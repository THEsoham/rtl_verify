from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import re
import structlog
from rtl_verify.verification.verilator import Verilator

log = structlog.get_logger()

@dataclass
class CoverageReport:
    line_coverage: float | None
    branch_coverage: float | None  
    toggle_coverage: float | None
    functional_coverage: float | None
    uncovered_lines: list[tuple[str, int]]  # (filename, line_number)
    raw_data: str
    
    def meets_threshold(self, threshold: float) -> bool:
        if self.line_coverage is None:
            return False
        return self.line_coverage >= threshold
        
    def to_dict(self) -> dict:
        return asdict(self)

class CoverageCollector:
    def __init__(self, verilator: Verilator):
        self.verilator = verilator
        
    async def collect(self, rtl_sources: list[Path], work_dir: Path) -> CoverageReport:
        # Assuming Verilator run_sim produced a coverage.dat in work_dir
        cov_dat = work_dir / 'coverage.dat'
        if not cov_dat.exists():
            log.warning("coverage.dat not found", path=str(cov_dat))
            return CoverageReport(None, None, None, None, [], "")
            
        cov_data = await self.verilator.collect_coverage(cov_dat)
        report = self.parse_verilator_annotate(work_dir)
        report.raw_data = cov_data.raw_text
        if cov_data.line_coverage is not None:
            report.line_coverage = cov_data.line_coverage
        if cov_data.branch_coverage is not None:
            report.branch_coverage = cov_data.branch_coverage
            
        return report

    def parse_verilator_annotate(self, annotated_dir: Path) -> CoverageReport:
        uncovered_lines = []
        total_lines = 0
        covered_lines = 0
        
        for ann_file in annotated_dir.glob('*.v'):
            try:
                with open(ann_file, 'r', encoding='utf-8') as f:
                    for i, line in enumerate(f, 1):
                        # Lines starting with %000000 or a count mean executable
                        # Lines starting with tab/spaces without % are usually non-executable or uncovered based on format
                        match = re.match(r'^\s*%000000', line)
                        if match:
                            total_lines += 1
                            uncovered_lines.append((ann_file.name, i))
                            continue
                            
                        cov_match = re.match(r'^\s*%(\d+)', line)
                        if cov_match and int(cov_match.group(1)) > 0:
                            total_lines += 1
                            covered_lines += 1
            except Exception as e:
                log.error("Failed to parse annotated file", file=str(ann_file), error=str(e))
                
        line_cov = None
        if total_lines > 0:
            line_cov = (covered_lines / total_lines) * 100
            
        return CoverageReport(
            line_coverage=line_cov,
            branch_coverage=None,
            toggle_coverage=None,
            functional_coverage=None,
            uncovered_lines=uncovered_lines,
            raw_data=""
        )
