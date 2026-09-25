from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from rtl_verify.config import settings
import structlog

log = structlog.get_logger()

@dataclass
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    elapsed_ms: int

class SubprocessRunner:
    @staticmethod
    async def run(cmd: list[str], cwd: Path | None = None, timeout: int | None = None, input_data: str | None = None) -> ProcessResult:
        if settings.use_wsl:
            cmd = SubprocessRunner.wsl_wrap(cmd)
            
        cmd_str = ' '.join(cmd)
        log.debug("Running command", cmd=cmd_str, cwd=str(cwd) if cwd else None)
        
        start_time = time.time()
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE if input_data else None
            )
            
            async def communicate():
                return await process.communicate(input=input_data.encode() if input_data else None)
                
            if timeout is not None:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(communicate(), timeout=timeout)
            else:
                stdout_bytes, stderr_bytes = await communicate()
                
            stdout = stdout_bytes.decode(errors='replace') if stdout_bytes else ""
            stderr = stderr_bytes.decode(errors='replace') if stderr_bytes else ""
            
            elapsed_ms = int((time.time() - start_time) * 1000)
            
            return ProcessResult(
                returncode=process.returncode or 0,
                stdout=stdout,
                stderr=stderr,
                timed_out=False,
                elapsed_ms=elapsed_ms
            )
            
        except asyncio.TimeoutError:
            try:
                process.kill()
            except Exception:
                pass
            elapsed_ms = int((time.time() - start_time) * 1000)
            return ProcessResult(
                returncode=-1,
                stdout="",
                stderr="Command timed out",
                timed_out=True,
                elapsed_ms=elapsed_ms
            )
        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            log.error("Command execution failed", error=str(e), cmd=cmd_str)
            return ProcessResult(
                returncode=-1,
                stdout="",
                stderr=str(e),
                timed_out=False,
                elapsed_ms=elapsed_ms
            )
            
    @staticmethod  
    def wsl_wrap(cmd: list[str]) -> list[str]:
        if cmd[0] == 'wsl':
            return cmd
        return ['wsl'] + cmd
    
    @staticmethod
    def to_wsl_path(win_path: Path) -> str:
        if not settings.use_wsl:
            return str(win_path)
        path_str = str(win_path)
        if len(path_str) >= 2 and path_str[1] == ':':
            drive = path_str[0].lower()
            rest = path_str[2:].replace('\\', '/')
            return f"/mnt/{drive}{rest}"
        return path_str.replace('\\', '/')
