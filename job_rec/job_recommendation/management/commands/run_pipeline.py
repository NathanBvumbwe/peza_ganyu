from django.core.management.base import BaseCommand
import subprocess
import sys
import asyncio
from pathlib import Path

from job_recommendation.scraper.run_scrapers import main as run_scrapers_main

class Command(BaseCommand):
    help = 'Runs the full job recommendation pipeline: scrape, categorize, match.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting pipeline...'))

        # 1. Run scrapers
        self.stdout.write('Running scrapers...')
        awaitable = run_scrapers_main(run_scheduler=False)
        if asyncio.iscoroutine(awaitable):
            asyncio.run(awaitable)
        else:
            awaitable

        # 2. Categorize jobs
        self.stdout.write('Categorizing jobs...')
        BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent  # points to job_rec/
        script_path = BASE_DIR / 'job_recommendation' / 'model' / 'test_BERT3.py'
        subprocess.run([sys.executable, str(script_path)], check=True)

        # 3. Run matching for all users
        self.stdout.write('Matching users to jobs...')
        from job_recommendation.model2_reccomender.eish import batch_save_all_matches
        batch_save_all_matches(top_n=6)

        self.stdout.write(self.style.SUCCESS('Pipeline complete!'))
