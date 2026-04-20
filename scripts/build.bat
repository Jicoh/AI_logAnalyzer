@echo off
chcp 65001 >nul
echo ================================================
echo AI日志分析器打包脚本
echo ================================================
echo.

python scripts\build_package.py

echo.
echo 打包完成，按任意键退出...
pause >nul