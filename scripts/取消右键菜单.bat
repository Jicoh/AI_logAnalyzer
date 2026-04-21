@echo off
chcp 936 >/dev/null
echo ================================================
echo  Unregister AI Log Analyzer Context Menu
echo ================================================
echo.

echo Unregistering for all files...
reg delete "HKCR\*\shell\AILogAnalyzer" /f
echo   Done

echo Unregistering for directories...
reg delete "HKCR\Directory\shell\AILogAnalyzer" /f
echo   Done

echo Unregistering for directory background...
reg delete "HKCR\Directory\Background\shell\AILogAnalyzer" /f
echo   Done

echo.
echo ================================================
echo  Unregistration Complete!
echo ================================================
echo.
pause
