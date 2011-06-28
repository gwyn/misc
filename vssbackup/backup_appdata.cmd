@echo off
rem
rem Backup script for %APPDATA% in Windows 7
rem
rem Copyright (c)2010 by Gwyn Connor (gwyn.connor at googlemail.com)
rem License: GNU Lesser General Public License
rem          (http://www.gnu.org/copyleft/lesser.txt)
rem
rem This script creates a backup of your own user's %APPDATA% folder
rem (C:\Users\USERNAME\AppData\Roaming) to the target folder D:\Backup\AppData.
rem It needs to run as Administrator in order to create snapshots.
rem
rem Dependencies:
rem   vshadow.exe   (from Microsoft 7 SDK: Bin\x64\vsstools\vshadow.exe)
rem   dosdev.exe    (http://sourceforge.net/projects/vscsc/files/utilities/dosdev.zip/download)
rem   robocopy.exe  (installed with Windows 7)
rem
rem References:
rem   Backing Up Open Files on Windows with Rsync (and BackupPC)
rem     http://www.goodjobsucking.com/index.php?p=62
rem   Volume Shadow Copy Simple Client
rem     http://vscsc.sourceforge.net/
rem   VShadow Tool and Sample
rem     http://msdn.microsoft.com/en-us/library/bb530725%28v=vs.85%29.aspx
rem     http://msdn.microsoft.com/en-us/library/bb530726%28v=vs.85%29.aspx#accessing_nonpersistent_shadow_copies

set source=%APPDATA%
set target=D:\Backup\AppData
set markerprefix=!Backup

set vssscript=%~dpn0%.vss.cmd
set thisscript=%~0%
set lockfile=%~dpn0%.lock

if exist %lockfile% goto dobackup
echo backup running > %lockfile%

echo Creating non-persistent shadow copy of %source% ...
vshadow -script=%vssscript% -exec=%thisscript% %source:~0,2%
echo Non-persistent shadow copy removed.
echo Done.

del %vssscript%
del %lockfile%
exit

:dobackup
call %vssscript%
dosdev B: %SHADOW_DEVICE_1%
echo Backing up %SHADOW_DEVICE_1% (snapshot of %source%) to %target% ...
robocopy B%source:~1% "%target%" /MIR /NFL /NDL
dosdev /D B:

echo Writing backup marker to directory.
mkdir %target%\%markerprefix%_%date:~6,4%-%date:~3,2%-%date:~0,2%_%time:~0,2%%time:~3,2%
