@echo off
chcp 936 >/dev/null
echo ================================================
echo  Register AI Log Analyzer Context Menu
echo ================================================
echo.

set "EXE_PATH=%~dp0ai_log_analyzer.exe"

if not exist "%EXE_PATH%" (
    echo ERROR: Cannot find ai_log_analyzer.exe
    pause
    exit /b 1
)

echo Found: %EXE_PATH%
echo.

echo Registering for all files...
reg add "HKCR\*\shell\AILogAnalyzer" /ve /d "Analyze with AI Log Analyzer" /f
reg add "HKCR\*\shell\AILogAnalyzer\command" /ve /d "\"%EXE_PATH%\" web --analyze-path \"%%1\"" /f
echo   Done

echo Registering for directories...
reg add "HKCR\Directory\shell\AILogAnalyzer" /ve /d "Analyze with AI Log Analyzer" /f
reg add "HKCR\Directory\shell\AILogAnalyzer\command" /ve /d "\"%EXE_PATH%\" web --analyze-path \"%%1\"" /f
echo   Done

echo Registering for directory background...
reg add "HKCR\Directory\Background\shell\AILogAnalyzer" /ve /d "Analyze with AI Log Analyzer" /f
reg add "HKCR\Directory\Background\shell\AILogAnalyzer\command" /ve /d "\"%EXE_PATH%\" web --analyze-path \"%%V\"" /f
echo   Done

echo.
echo ================================================
echo  Registration Complete!
echo ================================================
echo.
echo You can now right-click on files or folders
echo to analyze them with AI Log Analyzer.
echo.
pause
