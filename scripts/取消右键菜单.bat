@echo off
chcp 65001 >nul
echo ================================================
echo 取消注册AI日志分析器右键菜单
echo ================================================
echo.

:: 删除文件类型关联
for %%ext in (zip tgz tar log txt) do (
    echo 取消注册 .%%ext 文件...
    reg delete "HKCR\.%%ext\shell\AILogAnalyzer" /f >nul 2>&1
)

:: 删除tar.gz关联
echo 取消注册 .tar.gz 文件...
reg delete "HKCR\.tar.gz\shell\AILogAnalyzer" /f >nul 2>&1

:: 删除文件夹关联
echo 取消注册文件夹右键菜单...
reg delete "HKCR\Directory\shell\AILogAnalyzer" /f >nul 2>&1

echo.
echo ================================================
echo 取消注册完成!
echo ================================================
echo.
echo 右键菜单项已移除
echo.
echo 按任意键退出...
pause >nul