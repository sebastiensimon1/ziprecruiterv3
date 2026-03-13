#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZipRecruiter Job Scraper v3 - Resilient Continuation
- Continues until target number of jobs is reached
- Better error handling - retries failed pages
- Stops only after multiple consecutive empty pages
- Enhanced EXCLUDE_TERMS filtering
- Remote detection with regex patterns (#LI-remote and Remote(...))
"""

from seleniumbase import Driver
import datetime
import random
import re
import logging
import csv
import os
import time
from urllib.parse import urlencode, quote_plus
from selenium.webdriver.common.by import By

current_timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)

remote_dict = {"ALL": "", "ON-SITE": "1", "REMOTE": "2", "HYBRID": "3"}


# ── Oxylabs Proxy Credentials ─────────────────────────────────────────────────
OXYLABS_HOST = "pr.oxylabs.io"
OXYLABS_PORT = "7777"
OXYLABS_USERNAME = "customer-testinguser_Ux6GO-cc-US"
OXYLABS_PASSWORD = "=Madrid926319301"
OXYLABS_PROXY = f"http://{OXYLABS_USERNAME}:{OXYLABS_PASSWORD}@{OXYLABS_HOST}:{OXYLABS_PORT}"
# ─────────────────────────────────────────────────────────────────────────────


EXCLUDE_TERMS = {
    'lead', 'manager', 'senior', 'principal', 'director', 'vp', 'vice president',
    'sr ', 'ciso', 'chief', 'level 2', 'tier 3', 'associate director', 'l3',
    'architecture', 'sme', 'architect', 'field', 'software developer',
    'data scientist', 'scientist', 'federal account executive',
    'full stack developer', 'traveling aircraft mechanic', 'software engineer',
    'human resources operations', 'ii', 'regional technical development specialist',
    'stock plan administrator', 'commissioning authority', 'salesforce', 'dir',
    'consultant', 'adjunct faculty', 'subject matter expert', 'staff', 'intern',
    'internship'
}

# Regex to detect remote work from location text or description
REMOTE_REGEX = re.compile(r'(Remote(?:\s*\([^)]+\))?)', re.IGNORECASE)
LI_REMOTE_REGEX = re.compile(r'#LI-Remote', re.IGNORECASE)


def should_exclude_job(title: str, exclude_terms: set) -> bool:
    """Check if job title contains any excluded terms."""
    title_lower = title.lower()
    for term in exclude_terms:
        if term in title_lower:
            return True
    return False


def detect_remote_from_text(text: str) -> str | None:
    """Detect remote work mode from location text or description using regex."""
    if REMOTE_REGEX.search(text):
        return "Remote"
    if LI_REMOTE_REGEX.search(text):
        return "Remote"
    return None


def create_filename(header, title, location, mode_of_work):
    date_strf = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    pos = title.replace(" ", "_")
    filename = f"Ziprecruiter_Jobs_{pos}_{location}"

    if mode_of_work != "ALL" and mode_of_work is not None:
        filename += f"_{mode_of_work}"

    filename += f"_{date_strf}.csv"

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
    return filename


class Ziprecruiter:
    BASE_URL = "https://www.ziprecruiter.com/jobs-search"

    jobs_collected = 0
    card_num = 0
    total_scraped = 0
    total_missed_card = 0
    total_skipped_title = 0
    total_skipped_easy = 0
    total_skipped_not_remote = 0
    abort_scraping = False

    def __init__(self, headless=True, except_titles=False, exclude_easy_apply=False, remote_only=False):
        self.headless = headless
        self.exclude_titles = except_titles
        self.exclude_easy_apply = exclude_easy_apply
        self.remote_only = remote_only
        self.driver = self._setup_driver()

    def _setup_driver(self):
        """Initializes SeleniumBase UC Mode with Oxylabs proxy."""
        return Driver(
            uc=True,
            headless2=self.headless,
            agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            proxy=OXYLABS_PROXY,
            no_sandbox=True,
        )

    def dismiss_popups(self):
        logging.info("Checking for pop-ups...")
        time.sleep(1)
        try:
            self.driver.send_keys("body", "\ue00c")
            logging.info("Sent Escape key.")
        except Exception as e:
            logging.error(f"Failed to dismiss popup: {e}")

    def quit(self):
        if self.driver:
            self.driver.quit()

    def extract_job_data(self, card):
        data = {
            "title": None,
            "company": None,
            "location": None,
            "salary": None,
            "mode_of_work": "Onsite",
            "link": None,
            "easy_apply": None,
            "employment_type": None,
            "description": None,
        }
        try:
            title_element = card.find_element(By.TAG_NAME, "h2")
            data["title"] = title_element.text.strip()

            logger.info(f"Processing card #{self.card_num}: {data['title']}")

            if should_exclude_job(data["title"], EXCLUDE_TERMS):
                logger.info(f"Skipping card #{self.card_num} (Excluded Title): {data['title']}")
                self.total_skipped_title += 1
                return None

            try:
                data["company"] = card.find_element(
                    By.CSS_SELECTOR, "a[data-testid='job-card-company']"
                ).text
            except Exception as e:
                logger.warning(f"Company name not found for card #{self.card_num}: {e}")
                data["company"] = "N/A"

            try:
                loc_element = card.find_element(
                    By.CSS_SELECTOR, "[data-testid='job-card-location']"
                )
                loc_container = loc_element.find_element(By.XPATH, "..")
                full_text = loc_container.text
                data["location"] = loc_element.text
            except Exception as e:
                logger.warning(f"Location not found for card #{self.card_num}: {e}")
                data["location"] = "N/A"
                full_text = ""

            try:
                data["salary"] = card.find_element(
                    By.XPATH, ".//p[contains(text(), '$')]"
                ).text
            except Exception:
                data["salary"] = None
                logger.info(f"Salary not found for card #{self.card_num}")

            # Detect remote using regex on location text
            remote_detected = detect_remote_from_text(full_text)
            if remote_detected:
                data["mode_of_work"] = "Remote"
            elif "Hybrid" in full_text:
                data["mode_of_work"] = "Hybrid"
            else:
                data["mode_of_work"] = "Onsite"

            try:
                card.find_element(By.CSS_SELECTOR, "button[aria-label^='View']").click()
                time.sleep(random.uniform(1.5, 2.5))
            except Exception as e:
                logger.error(f"Failed to click job card #{self.card_num}: {e}")
                self.total_missed_card += 1
                return None

            try:
                self.driver.wait_for_element(
                    "[data-testid='job-details-scroll-container']", timeout=5
                )
                data["description"] = self.driver.get_text(
                    "[data-testid='job-details-scroll-container']"
                )
            except Exception as e:
                logger.warning(f"Description not found for card #{self.card_num}: {e}")
                data["description"] = "N/A"

            # Also check description for #LI-Remote or Remote regex
            if data["description"] and data["mode_of_work"] != "Remote":
                desc_remote = detect_remote_from_text(data["description"])
                if desc_remote:
                    data["mode_of_work"] = "Remote"
                    logger.info(f"Card #{self.card_num} marked Remote via description regex")

            # Remote-only enforcement
            if self.remote_only and data["mode_of_work"] != "Remote":
                logger.info(
                    f"Skipping card #{self.card_num} (Not Remote: {data['mode_of_work']}): {data['title']}"
                )
                self.total_skipped_not_remote += 1
                return None

            apply_element = self.driver.find_element("[aria-label*='Apply']")
            apply_text = apply_element.text.strip().lower()
            data["easy_apply"] = True if "quick apply" in apply_text else False

            try:
                data["link"] = apply_element.get_attribute("href")
                if data["link"] is None:
                    raise Exception("Apply button does not have href link attribute")
            except Exception as e:
                logger.warning(f"Failed to get link from Apply button for card #{self.card_num}: {e}")
                try:
                    link_el = card.find_element(
                        By.CSS_SELECTOR, "[data-testid='job-card-title'], .job_link"
                    )
                    relative_url = link_el.get_attribute("href")
                    data["link"] = (
                        relative_url
                        if "http" in relative_url
                        else f"https://www.ziprecruiter.com{relative_url}"
                    )
                    time.sleep(1)
                except Exception:
                    data["link"] = None

            if data["easy_apply"] and self.exclude_easy_apply:
                self.total_skipped_easy += 1
                return None

            try:
                el_selector = "[data-testid='job-details-scroll-container'] p:contains('time'), [data-testid='job-details-scroll-container'] p:contains('Contract')"
                self.driver.wait_for_element(el_selector, timeout=3)
                data["employment_type"] = self.driver.get_text(el_selector)
            except Exception:
                data["employment_type"] = "N/A"
                logger.info(f"Employment type not found for card #{self.card_num}")

            self.total_scraped += 1
            return data

        except Exception as e:
            logger.error(f"Error extracting card #{self.card_num}: {e}")
            self.total_missed_card += 1
            return None

    def _generate_url(
        self,
        search,
        location,
        zip_apply_only,
        mode_of_work,
        radius,
        days,
        min_salary,
        max_salary,
        employment_type,
        experience_level,
        page,
    ):
        params = {
            "search": search,
            "location": location,
            "radius": radius,
        }
        params["refine_by_apply_type"] = "has_zipapply" if zip_apply_only else ""
        params["refine_by_location_type"] = mode_of_work if mode_of_work else ""
        params["days"] = days if days else ""
        params["refine_by_salary"] = min_salary if min_salary else ""
        params["refine_by_salary_ceil"] = max_salary if max_salary else ""

        if employment_type is None:
            params["refine_by_employment"] = "all"
        elif employment_type == "all":
            params["refine_by_employment"] = ""
        elif employment_type:
            params["refine_by_employment"] = f"employment_type:{employment_type}"

        params["refine_by_experience_level"] = (
            ",".join(experience_level) if experience_level else ""
        )
        params["page"] = f"{page}"

        return f"{self.BASE_URL}?{urlencode(params, quote_via=quote_plus)}"

    def scraper_zip_recruiter(
        self,
        *,
        search: str,
        location: str,
        zip_apply_only: bool = False,
        mode_of_work: str | None,
        radius: int = 5000,
        days: int | None = None,
        min_salary: int | None = 0,
        max_salary: int | None = 300000,
        employment_type: str | None,
        experience_level: list[str] | None = None,
        max_jobs: int | None = None,
        start_page: int = 0,
        output_file: str | None = None,
    ):
        header = [
            "title", "company", "location", "salary",
            "mode_of_work", "employment_type", "easy_apply",
            "link", "description",
        ]

        if output_file is None:
            output_file = create_filename(header, search, location, mode_of_work)
        else:
            with open(output_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(header)

        page = start_page
        consecutive_empty_pages = 0
        max_empty_pages = 3
        max_page_retries = 2

        all_jobs = []  # collect for API return

        try:
            while not self.abort_scraping:
                logger.info(f"Target: {self.total_scraped}/{max_jobs if max_jobs else 'unlimited'} jobs collected")

                retry_count = 0
                page_success = False

                while retry_count <= max_page_retries and not page_success:
                    try:
                        url = self._generate_url(
                            search=search,
                            location=location,
                            zip_apply_only=zip_apply_only,
                            mode_of_work=mode_of_work,
                            radius=radius,
                            days=days,
                            min_salary=min_salary,
                            max_salary=max_salary,
                            employment_type=employment_type,
                            experience_level=experience_level,
                            page=page,
                        )

                        self.driver.uc_open_with_reconnect(url, reconnect_time=6)
                        time.sleep(random.uniform(2, 4))
                        self.dismiss_popups()

                        # ── Bot-block / CAPTCHA detection ──────────────────
                        page_title = self.driver.get_title().lower()
                        page_src   = self.driver.get_page_source().lower()
                        if any(kw in page_title for kw in ["captcha", "access denied", "robot", "blocked", "just a moment"]):
                            logger.error(f"Bot-block detected on page {page} — title: '{page_title}'. Stopping.")
                            self.abort_scraping = True
                            break

                        # ── Try multiple container selectors (ZR may change their HTML) ─
                        container_selector = None
                        for sel in [
                            "section[class*='job_results_two_pane']",
                            "[data-testid='job-search-results']",
                            ".job_results",
                            "[class*='jobList']",
                            "[class*='jobs-list']",
                        ]:
                            try:
                                self.driver.wait_for_element(sel, timeout=10)
                                container_selector = sel
                                logger.info(f"Container found with selector: {sel}")
                                break
                            except Exception:
                                continue

                        if not container_selector:
                            logger.error(f"No job container found on page {page}. Page title: '{self.driver.get_title()}'")
                            raise Exception("Job container not found — possible bot block or page structure change")

                        job_cards = self.driver.find_elements(
                            f"{container_selector} > div, {container_selector} [data-testid='job-card']"
                        )

                        if not job_cards or len(job_cards) <= 2:
                            consecutive_empty_pages += 1
                            logger.warning(f"Page {page} has no job cards. Empty page count: {consecutive_empty_pages}/{max_empty_pages}")
                            if consecutive_empty_pages >= max_empty_pages:
                                logger.info(f"Reached {max_empty_pages} consecutive empty pages. Stopping.")
                                self.abort_scraping = True
                            break

                        logger.info(f"Found {len(job_cards)} job cards on page {page}. Processing...")
                        consecutive_empty_pages = 0
                        page_success = True

                        jobs_data = []
                        for card in job_cards[1:-2]:
                            self.card_num += 1
                            job_info = self.extract_job_data(card)

                            if job_info:
                                jobs_data.append(job_info)
                                all_jobs.append(job_info)
                                logger.info(f"Accepted job #{self.total_scraped}/{max_jobs if max_jobs else 'unlimited'}")

                            if max_jobs and self.total_scraped >= max_jobs:
                                self.abort_scraping = True
                                logger.info(f"TARGET REACHED! Collected {max_jobs} jobs!")
                                break

                        if jobs_data:
                            with open(output_file, "a", newline="", encoding="utf-8") as f:
                                writer = csv.DictWriter(f, fieldnames=header)
                                writer.writerows(jobs_data)

                        logging.info(f"Jobs scraped this batch: {len(jobs_data)}")
                        logging.info(f"Running total scraped: {self.total_scraped}")
                        logging.info(f"[SAVED] Batch saved to {output_file}")

                    except Exception as e:
                        retry_count += 1
                        if retry_count <= max_page_retries:
                            logger.warning(f"Error on page {page} (attempt {retry_count}/{max_page_retries}): {e}")
                            logger.info(f"Retrying page {page} in 5 seconds...")
                            time.sleep(5)
                        else:
                            logger.error(f"Failed to load page {page} after {max_page_retries} retries. Skipping.")
                            break

                if self.abort_scraping:
                    break

                time.sleep(random.randint(2, 5))
                page += 1

        except Exception as e:
            logging.error(f"Fatal error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if self.driver:
                logging.info("=" * 60)
                logging.info("FINAL STATISTICS")
                logging.info("=" * 60)
                logging.info(f"Total cards processed:          {self.card_num}")
                logging.info(f"Total jobs scraped:             {self.total_scraped}")
                logging.info(f"Total cards missed:             {self.total_missed_card}")
                logging.info(f"Total skipped (excluded title): {self.total_skipped_title}")
                logging.info(f"Total skipped (not remote):     {self.total_skipped_not_remote}")
                logging.info(f"Total skipped (easy apply):     {self.total_skipped_easy}")
                logging.info("=" * 60)
                self.quit()

        return all_jobs


# ── Interactive CLI entry point ──────────────────────────────────────────────

def prompt_required(prompt_text):
    while True:
        value = input(prompt_text).strip()
        if value:
            return value
        print("This field is required. Please try again.")


if __name__ == "__main__":

    logging.info("=" * 60)
    logging.info(" Welcome to ZipRecruiter Job Scraper v3")
    logging.info(" Resilient Continuation - Hunts Until Target Reached!")
    logging.info("=" * 60)
    print()

    title = prompt_required("Enter job title (e.g. Cybersecurity): ")

    location = "USA"
    logging.info(f"[DEFAULT] Location set to: {location}")

    max_jobs_input = input("Enter max number of jobs to scrape (press Enter for unlimited): ").strip()
    max_jobs = int(max_jobs_input) if max_jobs_input else None

    zipapply_only_input = input("Only show Easy/Quick Apply jobs? (y/n, default n): ").strip().lower()
    zipapply_only = zipapply_only_input == "y"

    remote_input = input("Remote only? (y/n, default=y): ").strip().lower()
    remote_only = remote_input not in ["n", "no"]
    mode_of_work = "remote" if remote_only else None

    start_page_input = input("Enter starting page number (press Enter to start from 0): ").strip()
    start_page = int(start_page_input) if start_page_input else 0

    headless_mode = input("Run in headless mode (invisible browser)? (y/n, default=n): ").strip().lower()
    headless = headless_mode not in ["n", "no"]

    logging.info(f"[DEFAULT] Remote only: {remote_only}")
    logging.info(f"[DEFAULT] Employment type: full_time")
    logging.info("[FILTER] Exclude Title enabled (always on)")
    logging.info("[FILTER] Exclude Easy Apply jobs (always on)")

    obj = Ziprecruiter(
        headless=headless,
        except_titles=True,
        exclude_easy_apply=True,
        remote_only=remote_only,
    )

    logger.info(f"Start time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    start_time = datetime.datetime.now()

    obj.scraper_zip_recruiter(
        search=title,
        location=location,
        zip_apply_only=zipapply_only,
        mode_of_work=mode_of_work,
        radius=5000,
        days=None,
        min_salary=None,
        max_salary=None,
        employment_type="full_time",
        experience_level=None,
        max_jobs=max_jobs,
        start_page=start_page,
    )

    endtime = datetime.datetime.now() - start_time
    logger.info(f"Total time taken: {endtime}")
