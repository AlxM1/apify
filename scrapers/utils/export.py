"""Export utility for scraper results."""

import json
import logging
from datetime import datetime
from pathlib import Path

from scrapers.base import ScraperResult

logger = logging.getLogger(__name__)


class Exporter:
    """Export scraper results to various formats."""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def to_json(
        self, results: list[ScraperResult], filename: str | None = None
    ) -> str:
        path = self._get_path(results, filename, ".json")
        with open(path, "w") as f:
            json.dump([r.to_dict() for r in results], f, indent=2)
        logger.info(f"Exported {len(results)} results to {path}")
        return str(path)

    def to_jsonl(
        self, results: list[ScraperResult], filename: str | None = None
    ) -> str:
        path = self._get_path(results, filename, ".jsonl")
        with open(path, "w") as f:
            for r in results:
                f.write(json.dumps(r.to_dict()) + "\n")
        logger.info(f"Exported {len(results)} results to {path}")
        return str(path)

    def to_csv(
        self, results: list[ScraperResult], filename: str | None = None
    ) -> str:
        import pandas as pd

        path = self._get_path(results, filename, ".csv")
        rows = [r.to_dict() for r in results]
        df = pd.json_normalize(rows)
        df.to_csv(path, index=False)
        logger.info(f"Exported {len(results)} results to {path}")
        return str(path)

    def _get_path(
        self,
        results: list[ScraperResult],
        filename: str | None,
        ext: str,
    ) -> Path:
        if filename:
            return self.output_dir / f"{filename}{ext}"
        platform = results[0].platform if results else "unknown"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.output_dir / f"{platform}_{ts}{ext}"
