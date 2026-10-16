@echo off
title Remote Server Executor (ServeEverything) in virtual python environment for MIM/ PyJab 
rem This start ServeEverything script should be run within the virtual python environment folder, on the same level as the 'scripts' folders

rem Navigate to the current script directory (needed when running from registry on startup)
set directorypath=%~dp0
cd /d %directorypath%
echo Current script directory is %directorypath%

cd "%cd%\Scripts"
echo Virtual Python environment path is %cd%
call activate.bat
echo *** Start the ServeEverything Remote Server... ***
python -m serve_everything.remote.server_executor