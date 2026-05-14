"""
日志文件工具模块
提供日志文件上传、准备等独立工具函数，从OrchestratorAgent中解耦
"""

import os
from typing import Dict

from src.utils import get_logger

logger = get_logger('log_file_tool')


def upload_log_file(
    file_path: str,
    work_dir: str,
    user_id: str,
    session_state: Dict,
    session_manager,
    session_id: str
) -> Dict:
    """
    处理日志文件上传，准备到temp目录供后续分析

    Args:
        file_path: 日志文件路径
        work_dir: 会话工作目录
        user_id: 用户ID
        session_state: 会话状态字典
        session_manager: 会话管理器
        session_id: 会话ID

    Returns:
        Dict: 上传结果
    """
    if not file_path:
        return {"error": "file_path不能为空"}

    import shutil
    from src.utils.file_utils import (
        create_work_directory, extract_archive_recursive,
        get_file_category, allowed_log_file, find_log_files_in_directory,
        get_user_data_dir
    )

    filename = os.path.basename(file_path)

    if not allowed_log_file(filename):
        return {
            "error": f"文件 '{filename}' 不是支持的日志格式。",
            "detail": "支持的格式：.tar.gz, .tar, .zip, .tgz, .txt, .log",
            "suggestion": "请上传日志文件或包含日志的压缩包后再进行分析。"
        }

    file_category = get_file_category(filename)
    src_path = file_path

    # 检查文件是否已在工作目录中，若不在则复制
    src_real_path = os.path.realpath(file_path)
    work_dir_real_path = os.path.realpath(work_dir)
    file_in_work_dir = src_real_path.startswith(work_dir_real_path + os.sep) or src_real_path == work_dir_real_path

    if not file_in_work_dir:
        dest_path = os.path.join(work_dir, filename)
        try:
            shutil.copy2(file_path, dest_path)
            src_path = dest_path
            logger.info(f"复制文件到工作目录: {filename}")
        except Exception as e:
            logger.error(f"复制文件失败: {str(e)}")
            return {"error": f"复制文件失败: {str(e)}"}
    else:
        logger.info(f"文件已在工作目录中: {filename}")

    # 更新上传文件记录
    uploaded_files = session_state.get("uploaded_files", [])
    if filename not in uploaded_files:
        uploaded_files.append(filename)
        session_state["uploaded_files"] = uploaded_files

    # 创建 temp 工作目录
    temp_base = get_user_data_dir(user_id, 'temp')
    temp_work_dir = create_work_directory(temp_base, filename)
    log_file_paths = []

    try:
        if file_category == 'archive':
            extract_archive_recursive(src_path, temp_work_dir)
            log_file_paths.extend(find_log_files_in_directory(temp_work_dir))
        else:
            dest_path = os.path.join(temp_work_dir, filename)
            shutil.copy2(src_path, dest_path)
            log_file_paths.append(dest_path)

        # 一次性更新 session state
        session_state["temp_work_dir"] = temp_work_dir
        session_state["log_file_paths"] = log_file_paths
        session_manager.update_state(session_id, {
            "uploaded_files": uploaded_files,
            "temp_work_dir": temp_work_dir,
            "log_file_paths": log_file_paths
        })

        logger.info(f"文件已准备到temp目录: {temp_work_dir}, 日志文件数: {len(log_file_paths)}")

        return {
            "success": True,
            "filename": filename,
            "work_dir_path": src_path,
            "temp_work_dir": temp_work_dir,
            "log_file_paths": log_file_paths,
            "message": f"文件已准备完成，可进行分析: {filename}"
        }

    except Exception as e:
        logger.error(f"文件准备失败: {str(e)}")
        return {"error": f"文件准备失败: {str(e)}"}


def prepare_log_analyzer(session_state: Dict) -> Dict:
    """
    为log_analyzer准备执行环境

    Args:
        session_state: 会话状态字典

    Returns:
        Dict: 包含 temp_work_dir, log_files 的字典，或者错误信息
    """
    # 检查是否有准备错误
    prepare_error = session_state.get("prepare_error")
    if prepare_error:
        return {"error": prepare_error}

    # 使用已有的log_file_paths（由upload_log_file工具设置）
    temp_work_dir = session_state.get("temp_work_dir", "")
    log_files = session_state.get("log_file_paths", [])

    if not log_files:
        return {"error": "没有可分析的日志文件，请先通过upload_log_file工具指定要分析的文件"}

    logger.info(f"使用已准备的日志文件: {len(log_files)} 个")
    return {
        "temp_work_dir": temp_work_dir,
        "log_files": log_files
    }
