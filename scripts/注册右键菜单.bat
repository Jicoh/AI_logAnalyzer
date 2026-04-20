@echo off
chcp 65001 >nul
echo ================================================
echo 注册AI日志分析器右键菜单
echo ================================================
echo.

:: 获取当前目录
set "EXE_PATH=%~dp0ai_log_analyzer.exe"

:: 检查exe是否存在
if not exist "%EXE_PATH%" (
    echo 错误: 找不到 ai_log_analyzer.exe
    echo 请确保此脚本在打包文件夹中运行
    echo.
    pause
    exit /b 1
)

echo 找到程序: %EXE_PATH%
echo.

:: 注册压缩文件类型 - zip
echo 注册 .zip 文件...
reg add "HKCR\.zip\shell\AILogAnalyzer" /ve /d "使用AI日志分析器分析" /f >nul 2>&1
reg add "HKCR\.zip\shell\AILogAnalyzer\command" /ve /d "\"%EXE_PATH%\" web --analyze-path \"%%1\"" /f >nul 2>&1
echo   完成: .zip

:: 注册 tar.gz 类型（特殊处理，因为有两个扩展名）
echo 注册 .tar.gz 文件...
reg add "HKCR\.tar.gz\shell\AILogAnalyzer" /ve /d "使用AI日志分析器分析" /f >nul 2>&1
reg add "HKCR\.tar.gz\shell\AILogAnalyzer\command" /ve /d "\"%EXE_PATH%\" web --analyze-path \"%%1\"" /f >nul 2>&1
echo   完成: .tar.gz

:: 注册其他压缩类型
for %%ext in (tgz tar) do (
    echo 注册 .%%ext 文件...
    reg add "HKCR\.%%ext\shell\AILogAnalyzer" /ve /d "使用AI日志分析器分析" /f >nul 2>&1
    reg add "HKCR\.%%ext\shell\AILogAnalyzer\command" /ve /d "\"%EXE_PATH%\" web --analyze-path \"%%1\"" /f >nul 2>&1
    echo   完成: .%%ext
)

:: 注册日志文件类型
for %%ext in (log txt) do (
    echo 注册 .%%ext 文件...
    reg add "HKCR\.%%ext\shell\AILogAnalyzer" /ve /d "使用AI日志分析器分析" /f >nul 2>&1
    reg add "HKCR\.%%ext\shell\AILogAnalyzer\command" /ve /d "\"%EXE_PATH%\" web --analyze-path \"%%1\"" /f >nul 2>&1
    echo   完成: .%%ext
)

:: 注册文件夹右键菜单
echo 注册文件夹右键菜单...
reg add "HKCR\Directory\shell\AILogAnalyzer" /ve /d "使用AI日志分析器分析" /f >nul 2>&1
reg add "HKCR\Directory\shell\AILogAnalyzer\command" /ve /d "\"%EXE_PATH%\" web --analyze-path \"%%1\"" /f >nul 2>&1
echo   完成: Directory

echo.
echo ================================================
echo 注册完成!
echo ================================================
echo.
echo 现在可以右键点击以下类型进行快速分析:
echo   - 压缩包: .zip, .tar.gz, .tgz, .tar
echo   - 日志文件: .log, .txt
echo   - 文件夹
echo.
echo 按任意键退出...
pause >nul