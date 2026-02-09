#!/usr/bin/env python3
"""CLI entry point for running scrapers."""

import asyncio
import json
import logging
import sys

import click
from rich.console import Console
from rich.table import Table
from rich.logging import RichHandler

from config.settings import PLATFORMS, get_scraper_class
from scrapers.base import ScraperConfig

console = Console()


def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(rich_tracebacks=True, console=console)],
    )


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
def cli(verbose):
    """Social Media Scraper Suite - Free Apify replacement."""
    setup_logging(verbose)


@cli.command()
def platforms():
    """List all available platforms."""
    table = Table(title="Available Platforms")
    table.add_column("#", style="dim", width=4)
    table.add_column("Platform", style="cyan")
    table.add_column("Rate Limit", style="green")

    for i, (name, info) in enumerate(PLATFORMS.items(), 1):
        table.add_row(str(i), name, f"{info['rate_limit']} req/s")

    console.print(table)
    console.print(f"\n[bold]{len(PLATFORMS)}[/bold] platforms available.")


@cli.command()
@click.argument("platform")
@click.argument("action", type=click.Choice(["profile", "posts", "search"]))
@click.argument("target")
@click.option("-n", "--max-results", default=50, help="Max results to fetch")
@click.option("-o", "--output", default="json", type=click.Choice(["json", "jsonl", "csv"]))
@click.option("--output-dir", default="output", help="Output directory")
@click.option("--proxy", default=None, help="Proxy URL (e.g. http://host:port)")
@click.option("--delay", default=1.0, help="Delay between requests in seconds")
@click.option("--headless/--no-headless", default=True, help="Run browser headless")
def scrape(platform, action, target, max_results, output, output_dir, proxy, delay, headless):
    """Run a scraper.

    PLATFORM: Platform name (e.g. youtube, reddit, twitter)
    ACTION:   One of 'profile', 'posts', 'search'
    TARGET:   URL, username, query, or identifier
    """
    config = ScraperConfig(
        max_results=max_results,
        proxy=proxy,
        output_format=output,
        output_dir=output_dir,
        delay_between_requests=delay,
        headless=headless,
    )

    scraper_cls = get_scraper_class(platform)
    asyncio.run(_run_scrape(scraper_cls, config, action, target, max_results))


async def _run_scrape(scraper_cls, config, action, target, max_results):
    async with scraper_cls(config) as scraper:
        console.print(
            f"[bold cyan]Scraping[/bold cyan] {scraper.platform_name} "
            f"| action={action} | target={target} | max={max_results}"
        )

        if action == "profile":
            results = await scraper.scrape_profile(target)
        elif action == "posts":
            results = await scraper.scrape_posts(target, max_results)
        elif action == "search":
            results = await scraper.search(target, max_results)
        else:
            console.print(f"[red]Unknown action: {action}[/red]")
            return

        if results:
            path = scraper.export(results)
            console.print(
                f"[bold green]Done![/bold green] "
                f"{len(results)} results exported to {path}"
            )
        else:
            console.print("[yellow]No results found.[/yellow]")


if __name__ == "__main__":
    cli()
