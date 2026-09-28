"""Product-bound AliExpress documents; stored locally, never auto-certified."""
import hashlib
import json
from io import BytesIO
from pathlib import Path
from functools import lru_cache
from zipfile import ZipFile
from xml.etree import ElementTree

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from pypdf import PdfReader

from .db import get_db
from .models import Asset, ProductMaster
from .storage import validate_image

router = APIRouter()
ROOT = Path(__file__).resolve().parents[1] / "data" / "compliance"
ROLES = {"label": "外包装/标签图", "reach": "REACH 检测报告", "other": "其他资质证明"}

def product_check(db, product_id):
    product = db.get(ProductMaster, product_id)
    if not product:
        raise HTTPException(404, "商品不存在")
    if json.loads(product.import_parameters_json or "{}").get("_platform") != "ALIEXPRESS":
        raise HTTPException(409, "此入口仅用于速卖通商品，不修改TEMU资料")

def documents(db, product_id):
    return list(db.scalars(select(Asset).where(Asset.product_id == product_id, Asset.asset_type == "COMPLIANCE").order_by(Asset.id.desc())))

def payload(asset):
    return {"id": asset.id, "label": ROLES[asset.role], "kind": asset.role, "size": asset.byte_size, "mime": asset.mime_type, **json.loads(asset.source_url)}

@lru_cache(maxsize=1)
def ocr_engine():
    from rapidocr import RapidOCR
    return RapidOCR()

def read_image(content):
    result = ocr_engine()(content)
    return "\n".join(result.txts or [])[:12000]

def read_pptx(content):
    with ZipFile(BytesIO(content)) as archive:
        slides = [entry for entry in archive.infolist() if entry.filename.startswith('ppt/slides/slide') and entry.filename.endswith('.xml')]
        if len(slides) > 100 or sum(entry.file_size for entry in slides) > 10 * 1024 * 1024:
            raise ValueError('演示文稿过大')
        texts = []
        for entry in slides:
            root = ElementTree.fromstring(archive.read(entry))
            texts.extend(element.text for element in root.iter() if element.tag.endswith('}t') and element.text)
        return chr(10).join(texts)[:12000]

@router.get("/api/products/{product_id}/compliance")
def list_files(product_id: int, db: Session = Depends(get_db)):
    product_check(db, product_id)
    return [payload(a) for a in documents(db, product_id)]

@router.get("/api/compliance-library")
def library(db: Session = Depends(get_db)):
    assets = db.scalars(select(Asset).where(Asset.asset_type == "COMPLIANCE").order_by(Asset.id.desc())).all()
    return [{**payload(asset), "product_id": asset.product_id} for asset in assets]

@router.post("/api/products/{product_id}/compliance/{kind}/reuse/{asset_id}")
def reuse(product_id: int, kind: str, asset_id: int, db: Session = Depends(get_db)):
    product_check(db, product_id)
    source = db.get(Asset, asset_id)
    if kind not in ROLES or not source or source.asset_type != "COMPLIANCE" or source.role != kind:
        raise HTTPException(404, "Missing reusable file")
    for previous in documents(db, product_id):
        if previous.role == kind:
            db.delete(previous)
    asset = Asset(product_id=product_id, asset_type="COMPLIANCE", role=kind, storage_key=source.storage_key,
        sha256=source.sha256, mime_type=source.mime_type, width=source.width, height=source.height,
        byte_size=source.byte_size, source_url=source.source_url, mirror_status="MIRRORED", rights_status="UNKNOWN")
    db.add(asset); db.commit(); db.refresh(asset)
    return payload(asset)

@router.put("/api/products/{product_id}/compliance/{kind}")
def upload(product_id: int, kind: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    product_check(db, product_id)
    if kind not in ROLES:
        raise HTTPException(422, "未知材料类型")
    limit = (3 if kind == "label" else 20) * 1024 * 1024
    content = file.file.read(limit + 1)
    if not content or len(content) > limit:
        raise HTTPException(413, f"文件必须非空且不超过{limit // 1024 // 1024}MB")
    text = ""
    width = height = None
    try:
        if content.startswith(b"%PDF-"):
            if kind == "label":
                raise ValueError("包装标签请上传真实图片")
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted or len(reader.pages) > 100:
                raise ValueError("请上传未加密且不超过100页的PDF")
            mime = "application/pdf"
            text = "\n".join((page.extract_text() or "")[:12000] for page in reader.pages[:20])[:12000]
            status = "已提取PDF文字（最多前20页）" if text.strip() else "扫描PDF未提取到文字，请人工核对"
        elif content.startswith(b'PK') and (file.filename or '').lower().endswith('.pptx'):
            if kind == 'label':
                raise ValueError('包装标签请上传真实图片')
            mime = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
            text = read_pptx(content)
            status = '已提取PPTX文字' if text.strip() else 'PPTX未提取到文字，请人工核对'
        elif content.startswith(bytes.fromhex('D0CF11E0A1B11AE1')) and (file.filename or '').lower().endswith('.ppt'):
            if kind == 'label':
                raise ValueError('包装标签请上传真实图片')
            mime = 'application/vnd.ms-powerpoint'
            status = '旧版PPT已保存，无法自动读取，请人工核对或转换为PPTX'
        else:
            meta = validate_image(content)
            mime, width, height = meta['mime_type'], meta['width'], meta['height']
            try:
                text = read_image(content)
                status = "已识别图片文字" if text.strip() else "图片未识别到文字，请人工核对"
            except Exception:
                status = "图片已保存，文字识别暂不可用，请人工核对"
    except Exception as exc:
        raise HTTPException(422, "文件无法读取，请检查格式或是否损坏：" + str(exc)[:120]) from exc
    digest = hashlib.sha256(content).hexdigest()
    ROOT.mkdir(parents=True, exist_ok=True)
    key = f"{product_id}-{digest}"
    (ROOT / key).write_bytes(content)
    for previous in documents(db, product_id):
        if previous.role == kind:
            db.delete(previous)
    asset = Asset(product_id=product_id, asset_type="COMPLIANCE", role=kind, storage_key=key,
        sha256=digest, mime_type=mime, width=width, height=height, byte_size=len(content),
        source_url=json.dumps({"filename": (file.filename or 'document').replace('\\','/').split('/')[-1], "text": text, "recognition": status}, ensure_ascii=False),
        mirror_status="MIRRORED", rights_status="UNKNOWN")
    db.add(asset); db.commit(); db.refresh(asset)
    return payload(asset)

@router.get("/api/products/{product_id}/compliance/files/{asset_id}")
def content(product_id: int, asset_id: int, db: Session = Depends(get_db)):
    product_check(db, product_id)
    asset = next((a for a in documents(db, product_id) if a.id == asset_id), None)
    if not asset:
        raise HTTPException(404, "文件不存在")
    return Response((ROOT / asset.storage_key).read_bytes(), media_type=asset.mime_type, headers={"X-Content-Type-Options": "nosniff"})

@router.delete("/api/products/{product_id}/compliance/files/{asset_id}", status_code=204)
def delete(product_id: int, asset_id: int, db: Session = Depends(get_db)):
    product_check(db, product_id)
    asset = next((a for a in documents(db, product_id) if a.id == asset_id), None)
    if not asset:
        raise HTTPException(404, "文件不存在")
    db.delete(asset); db.commit()
