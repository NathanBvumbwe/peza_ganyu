from django.core.management.base import BaseCommand
import subprocess
import sys
import asyncio
from job_recommendation.scraper.run_scrapers import main as run_scrapers_main

class Command(BaseCommand):
    help = 'Runs the full job recommendation pipeline: scrape, categorize, match.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting pipeline...'))

        # 1. Run scrapers (corrected path)
        self.stdout.write('Running scrapers...')
        awaitable = run_scrapers_main(run_scheduler=False)
        if asyncio.iscoroutine(awaitable):
            asyncio.run(awaitable)
        else:
            awaitable  # fallback, but should always be a coroutine

        # 2. Categorize jobs
        self.stdout.write('Categorizing jobs...')
        subprocess.run([sys.executable, 'job_rec/job_recommendation/model/test_BERT3.py'], check=True)

        # 3. Run matching for all users (update recommendations after new jobs)
        self.stdout.write('Matching users to jobs...')
        from job_recommendation.model2_reccomender.eish import batch_save_all_matches
        batch_save_all_matches(top_n=6)

        self.stdout.write(self.style.SUCCESS('Pipeline complete!')) 