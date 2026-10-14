@echo off
echo ============================================================
echo  DIY eDiscovery Hub - Starting Background Services
echo ============================================================
echo.
echo Starting OpenSearch...
start "OpenSearch" cmd /c "cd /d "C:\Tools\opensearch-2.19.1" && bin\opensearch.bat"
echo Waiting 15 seconds for OpenSearch to initialize...
timeout /t 15 /nobreak >nul
echo.
echo Starting Apache Tika Server...
start "Tika Server" cmd /c "java -jar "C:\Tools\tika\tika-server-standard-3.2.3.jar" --host 0.0.0.0 --port 9998"
echo Waiting 10 seconds for Tika to initialize...
timeout /t 10 /nobreak >nul
echo.
echo ============================================================
echo  Services started. You can now launch the platform.
echo  To stop services, close the OpenSearch and Tika windows.
echo ============================================================
echo.
pause
