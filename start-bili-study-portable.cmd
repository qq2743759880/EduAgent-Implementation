@echo off
setlocal
pushd "%~dp0"
python deploy\portable.py up %*
set "START_RESULT=%ERRORLEVEL%"
popd
exit /b %START_RESULT%
