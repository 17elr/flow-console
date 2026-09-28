param(
    [ValidateSet('Inspect', 'Validate', 'Apply', 'SelfTest')]
    [string]$Mode = 'Inspect',
    [string]$Sku = '042+BX03'
)

$ErrorActionPreference = 'Stop'
$category = '珠宝饰品及配件 (Jewelry & Accessories)/流行饰品 (Fashion Jewelry)/项链 (Necklace)'
$countries = @('西班牙', '法国', '巴西', '韩国', '美国', '中东六国')
$nativeAttributes = [ordered]@{
    '产地（国家或地区）(Origin)' = '中国大陆(Origin)'
    '中国省份(CN)' = '广东'
    '金属类型(Metals Type)' = '铜'
    '性别(Gender)' = '女'
    '项链类型(Necklace Type)' = '吊坠项链'
    '材质(Material)' = '不锈钢'
    '扣合类型(Clasp Type)' = '龙虾爪扣'
    '镶嵌材质(Setting Material)' = '人工宝石/半宝石'
    '高关注化学品(High-concerned chemical)' = '无'
    '珠宝或饰品(Fine or Fashion)' = 'fashion'
    '产品类型(Item Type)' = '项链'
    '风格(Style)' = 'TRENDY'
    '链类型(Chain Type)' = 'O字链'
    '形状\图案(Shape\pattern)' = '心型'
    '兼容性(Compatibility)' = '全兼容'
    '场合(Occasion)' = '生日'
    '认证(Certification)' = 'REACH检测报告'
}

function Test-AllSelected([string[]]$selected) {
    foreach ($name in @('全选') + $countries) {
        if ($name -notin $selected) { return $false }
    }
    return $true
}

function Assert-ImportReady([hashtable]$verified) {
    $required = @('NativeAttributes', 'SkuPriceStockLogistics', 'ProductImages')
    $missing = @($required | Where-Object { -not $verified[$_] })
    if ($missing.Count) {
        throw "Apply unavailable until these editor fields are verified: $($missing -join ', '). No remote changes were made."
    }
}

if ($Mode -eq 'SelfTest') {
    $all = @('全选') + $countries
    if (-not (Test-AllSelected $all) -or (Test-AllSelected $all[0..5])) {
        throw 'Country selection self-check failed.'
    }
    $refused = $false
    try { Assert-ImportReady @{} } catch { $refused = $true }
    if (-not $refused) { throw 'Incomplete import readiness self-check failed.' }
    if ($nativeAttributes.Count -ne 17 -or @($nativeAttributes.Keys | Where-Object {
        -not $_ -or -not $nativeAttributes[$_]
    }).Count -gt 0 -or $nativeAttributes['形状\图案(Shape\pattern)'] -ne '心型') {
        throw 'Native attribute mapping self-check failed.'
    }
    'SelfTest OK'
    exit 0
}

if ($Mode -eq 'Apply') { Assert-ImportReady @{} }

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class MiaoshouMouse {
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint x, uint y, uint data, UIntPtr extra);
}
'@

function Get-Elements($root) {
    $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,
        [System.Windows.Automation.Condition]::TrueCondition)
}

function Get-EditValues($root) {
    $condition = [System.Windows.Automation.PropertyCondition]::new(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::Edit)
    foreach ($element in $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condition)) {
        $pattern = $null
        if ($element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$pattern)) {
            [pscustomobject]@{ Element = $element; Value = [string]$pattern.Current.Value }
        }
    }
}

function Find-Visible($root, [string]$name, [bool]$exact = $true) {
    $matches = @()
    $candidates = if ($exact) {
        $condition = [System.Windows.Automation.PropertyCondition]::new(
            [System.Windows.Automation.AutomationElement]::NameProperty, $name)
        $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condition)
    } else { Get-Elements $root }
    foreach ($element in $candidates) {
        try {
            $text = ([string]$element.Current.Name).Trim()
            if (($exact -and $text -eq $name) -or (-not $exact -and $text.Contains($name))) {
                $matches += $element
            }
        } catch [System.Windows.Automation.ElementNotAvailableException] { }
    }
    return $matches
}

function Get-NativeField($root, [string]$label) {
    $walker = [System.Windows.Automation.TreeWalker]::RawViewWalker
    $matches = @()
    foreach ($text in (Find-Visible $root $label)) {
        if ($text.Current.ControlType -ne [System.Windows.Automation.ControlType]::Text) { continue }
        $rect = $text.Current.BoundingRectangle
        $candidates = @(Get-EditValues $root) | Where-Object {
            $editRect = $_.Element.Current.BoundingRectangle
            [math]::Abs($editRect.Left - $rect.Left) -le 14 -and
            $editRect.Width -ge 880 -and
            $editRect.Top -ge $rect.Bottom -and $editRect.Top -lt ($rect.Bottom + 75)
        }
        if ($candidates.Count -ne 1) { continue }
        $edit = $candidates[0].Element
        $group = $walker.GetParent($edit)
        while ($group) {
            $pattern = $null
            if ($group.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$pattern)) {
                break
            }
            $group = $walker.GetParent($group)
        }
        if ($group -and $edit) { $matches += @{ Group = $group; Edit = $edit } }
    }
    if ($matches.Count -ne 1) { throw "Expected one native field '$label', found $($matches.Count)." }
    return $matches[0]
}

function Get-NativeValue($field) {
    $pattern = $field.Edit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
    $value = ([string]$pattern.Current.Value).Trim()
    if ($value) { return $value }
    $name = ([string]$field.Edit.Current.Name).Trim()
    if ($name -ne '请选择' -and $name -ne '请输入') { return $name }
    return ''
}

function Get-ExactOption($root, [string]$name) {
    $condition = [System.Windows.Automation.PropertyCondition]::new(
        [System.Windows.Automation.AutomationElement]::NameProperty, $name)
    $deadline = (Get-Date).AddSeconds(5)
    do {
        $matches = @($root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condition) |
            Where-Object { $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::ListItem -and
                -not $_.Current.IsOffscreen })
        if ($matches.Count -eq 1) { return $matches[0] }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)
    throw "Expected one dropdown option '$name', found $($matches.Count)."
}

function Open-NativeOptions($field, $window) {
    $field.Group.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
}

function Set-NativeField($root, $window, [string]$label, [string]$expected) {
    $field = Get-NativeField $root $label
    if ((Get-NativeValue $field) -eq $expected) { return }
    Open-NativeOptions $field $window
    $option = Get-ExactOption $root $expected
    $option.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
    $deadline = (Get-Date).AddSeconds(5)
    do {
        $actual = Get-NativeValue (Get-NativeField $root $label)
        if ($actual -eq $expected) { return }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)
    throw "Native field '$label' is '$actual', expected '$expected'. Nothing was saved."
}

function Click-Element($element, $window) {
    if ([MiaoshouMouse]::GetForegroundWindow() -ne $window.MainWindowHandle) {
        throw 'Focus the Miaoshou editor window before running Apply.'
    }
    $rect = $element.Current.BoundingRectangle
    if ($element.Current.IsOffscreen -or $rect.IsEmpty -or $rect.Width -le 0) {
        throw "Cannot click hidden element: $($element.Current.Name)"
    }
    $x = [int]($rect.Left + $rect.Width / 2)
    $y = [int]($rect.Top + $rect.Height / 2)
    [void][MiaoshouMouse]::SetCursorPos($x, $y)
    [MiaoshouMouse]::mouse_event(2, 0, 0, 0, [UIntPtr]::Zero)
    [MiaoshouMouse]::mouse_event(4, 0, 0, 0, [UIntPtr]::Zero)
}

function Get-Checkbox($root, [string]$name, $settings) {
    $found = @()
    $walker = [System.Windows.Automation.TreeWalker]::RawViewWalker
    foreach ($element in (Get-Elements $root)) {
        try {
            if ($element.Current.ControlType -ne [System.Windows.Automation.ControlType]::CheckBox -or
                -not ([string]$element.Current.Name).Trim().StartsWith($name)) { continue }
            $rect = $walker.GetParent($element).Current.BoundingRectangle
            if ($rect.Top -gt $settings.Top -and $rect.Bottom -lt $settings.Bottom) {
                $found += $element
            }
        } catch [System.Windows.Automation.ElementNotAvailableException] { }
    }
    if ($found.Count -ne 1) { throw "Expected one '$name' checkbox in 差异化设置, found $($found.Count)." }
    return $found[0]
}

function Get-SettingsBounds($root) {
    $heading = @(Find-Visible $root '差异化设置') | Select-Object -First 1
    if (-not $heading) { throw 'Cannot locate the 差异化设置 section.' }
    $next = @(Find-Visible $root '产品标题' $false) | Where-Object {
        $_.Current.BoundingRectangle.Top -gt $heading.Current.BoundingRectangle.Bottom
    } | Sort-Object { $_.Current.BoundingRectangle.Top } | Select-Object -First 1
    if (-not $heading -or -not $next) { throw 'Cannot locate the 差异化设置 section.' }
    return @{ Top = $heading.Current.BoundingRectangle.Top; Bottom = $next.Current.BoundingRectangle.Top }
}

function Get-SelectedCountries($root) {
    $bounds = Get-SettingsBounds $root
    $selected = @()
    foreach ($name in @('全选') + $countries) {
        $box = Get-Checkbox $root $name $bounds
        $pattern = $box.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
        if ($pattern.Current.ToggleState -eq [System.Windows.Automation.ToggleState]::On) {
            $selected += $name
        }
    }
    return $selected
}

$windows = @(Get-Process msedge -ErrorAction SilentlyContinue | Where-Object {
    $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -match '妙手'
})
if ($windows.Count -ne 1) { throw "Expected one Miaoshou Edge window, found $($windows.Count)." }
$window = $windows[0]
$root = [System.Windows.Automation.AutomationElement]::FromHandle($window.MainWindowHandle)
$editor = @(Find-Visible $root '类目&属性').Count -gt 0 -and
    @(Find-Visible $root '差异化设置').Count -gt 0
$editValues = @(Get-EditValues $root)
$skuVisible = @($editValues | Where-Object {
    $_.Value -match '^042(G|RG|S)\+BX03-(BE|BK|PK|RD|WE)$'
} | Select-Object -ExpandProperty Value -Unique).Count -eq 15
if (-not $editor -or -not $skuVisible) {
    throw "Open the AliExpress editor for $Sku in the active Edge tab first (editor=$editor, sku=$skuVisible)."
}

$categorySelected = @($editValues | Where-Object { $_.Value -eq $category }).Count -eq 1
$selected = @(Get-SelectedCountries $root)
if ($Mode -eq 'Inspect') {
    [pscustomobject]@{
        Sku = $Sku
        CategorySelected = $categorySelected
        SelectedCountries = $selected -join ', '
        AllCountriesSelected = Test-AllSelected $selected
    } | Format-List
    exit 0
}

if ($Mode -eq 'Validate') {
    if (-not $categorySelected) { throw "Select $category before validating native attributes." }
    $results = @()
    foreach ($entry in $nativeAttributes.GetEnumerator()) {
        $field = Get-NativeField $root $entry.Key
        $before = Get-NativeValue $field
        if ($before -ne $entry.Value) {
            Open-NativeOptions $field $window
            try { [void](Get-ExactOption $root $entry.Value) }
            finally { Open-NativeOptions $field $window }
        }
        if ((Get-NativeValue (Get-NativeField $root $entry.Key)) -ne $before) {
            throw "Validation changed '$($entry.Key)'; stop before saving."
        }
        $results += [pscustomobject]@{ Label = $entry.Key; Expected = $entry.Value; Current = $before }
    }
    $results | Format-Table -AutoSize
    'All 17 native labels and dropdown options exist; no product values were changed.'
    exit 0
}

if (-not $categorySelected) {
    $categoryLabel = @(Find-Visible $root '类目') | Select-Object -First 1
    if (-not $categoryLabel) { throw 'Cannot locate the category label.' }
    $labelRect = $categoryLabel.Current.BoundingRectangle
    $controls = @(Get-Elements $root) | Where-Object {
        try {
            $rect = $_.Current.BoundingRectangle
            -not $_.Current.IsOffscreen -and $rect.Top -ge $labelRect.Bottom -and
                $rect.Top -lt ($labelRect.Bottom + 100) -and
                $rect.Width -gt 200 -and $rect.Left -le ($labelRect.Left + 100) -and
                $_.Current.ControlType -in @(
                    [System.Windows.Automation.ControlType]::ComboBox,
                    [System.Windows.Automation.ControlType]::Edit)
        } catch [System.Windows.Automation.ElementNotAvailableException] { $false }
    } | Sort-Object { $_.Current.BoundingRectangle.Width } -Descending
    if ($controls.Count -lt 1) { throw 'Cannot locate the category selector.' }
    Click-Element $controls[0] $window
    foreach ($part in $category.Split('/')) {
        $deadline = (Get-Date).AddSeconds(8)
        do {
            $options = @(Find-Visible $root $part) | Where-Object {
                $_.Current.BoundingRectangle.Top -gt $labelRect.Bottom
            }
            if ($options.Count -gt 0) { break }
            Start-Sleep -Milliseconds 250
        } while ((Get-Date) -lt $deadline)
        if ($options.Count -ne 1) { throw "Cannot uniquely select category part '$part' ($($options.Count) matches)." }
        Click-Element $options[0] $window
        Start-Sleep -Milliseconds 300
    }
    $categorySelected = @(Get-EditValues $root | Where-Object { $_.Value -eq $category }).Count -eq 1
    if (-not $categorySelected) { throw "Category did not resolve to $category; nothing was saved." }
}

foreach ($entry in $nativeAttributes.GetEnumerator()) {
    Set-NativeField $root $window $entry.Key $entry.Value
}

if (-not (Test-AllSelected $selected)) {
    $bounds = Get-SettingsBounds $root
    $allBox = Get-Checkbox $root '全选' $bounds
    $toggle = $allBox.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
    if ($toggle.Current.ToggleState -ne [System.Windows.Automation.ToggleState]::On) {
        $toggle.Toggle()
    }
    $selected = @(Get-SelectedCountries $root)
    if (-not (Test-AllSelected $selected)) { throw 'Country selection incomplete; nothing was saved.' }
}

"Verified ${Sku}: $category; 全选 + $($countries -join ', '). Nothing was saved."
