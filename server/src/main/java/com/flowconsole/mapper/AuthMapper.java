package com.flowconsole.mapper;

import java.util.*;
import org.apache.ibatis.annotations.*;

public interface AuthMapper {
  @Select("SELECT * FROM app_user WHERE username=#{name}")
  Map<String, Object> username(String name);

  @Select("SELECT * FROM app_user WHERE id=#{id}")
  Map<String, Object> user(long id);

  @Select("SELECT id,username,role,active,auth_version FROM app_user ORDER BY id")
  List<Map<String, Object>> users();

  @Select("SELECT COUNT(*) FROM app_user")
  int count();

  @Update(
      "UPDATE app_user SET"
          + " password_hash=COALESCE(#{hash},password_hash),active=#{active},role=#{role},auth_version=auth_version+1"
          + " WHERE id=#{id}")
  int change(
      @Param("id") long id,
      @Param("hash") String hash,
      @Param("active") boolean active,
      @Param("role") String role);
}
