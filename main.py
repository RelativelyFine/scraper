import argparse
from re import I
from pcpartpicker_scraper.serialization import dataclass_to_dict, dataclass_from_dict
from pcpartpicker_scraper.scraper import Scraper
from pcpartpicker_scraper.parser import Parser
from pcpartpicker_scraper.mappings import part_classes
from tqdm import tqdm
from diskcache import Cache
from datetime import datetime
from pathlib import Path
import os
import json
import itertools
from concurrent.futures import ProcessPoolExecutor as Pool

html_doc = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Data</title>
  </head>
  <body>
  {}
  </body>
</html>"""


def scrape_part_region_combo(p):
    part = p[0]
    region = p[1]
    scraper = Scraper(
        "~/AppData/Local/Programs/Python/Python310/Scripts/chromedriver")
    cache = Cache("~/ppccache/")
    part_data = scraper.get_part_data(region, part)
    stored_parts = cache[region]
    stored_parts.update({part: part_data})
    cache[region] = stored_parts
    print(f"finished with {region}/{part}")


def scrape_part_data(pool_size):
    supported_parts = {"cpu", "cpu-cooler", "motherboard", "memory", "internal-hard-drive",
                       "video-card", "power-supply", "case", "wireless-network-card"}

    supported_regions = {"ca", "us"}

    cache = Cache("~/ppccache/")
    if "timestamp" in cache:
        timestamp = cache["timestamp"]
        if datetime.now().month > timestamp.month:
            cache.clear()
            cache["timestamp"] = datetime.now()
            print("Clearing cache...")
    else:
        cache.clear()
        cache["timestamp"] = datetime.now()
        print("Clearing cache...")

    for region in supported_regions:
        if region not in cache:
            cache[region] = {}

    to_scrape = list(itertools.product(supported_parts, supported_regions))
    total_to_scrape = len(to_scrape)
    to_scrape = list(filter(lambda x: x[0] not in cache[x[1]], to_scrape))
    pool = Pool(pool_size)
    print(
        f"About to scrape {len(to_scrape)}/{total_to_scrape} part+region combos that are not cached using {pool_size} concurrent requests")
    pool.map(scrape_part_region_combo, to_scrape)


def parse_part_data():
    cache = Cache("~/ppccache/")

    parsed_part_data = {}
    for region in tqdm(cache):
        if region == "timestamp":
            continue
        parsed_parts = {}
        part_data = cache[region]
        for part, part_data in part_data.items():
            manufacturers, parts = part_data
            parser = Parser(region, part, manufacturers)
            pparts = parser.parse(parts)
            parsed_parts[part] = pparts
        parsed_part_data[region] = parsed_parts
    parsed_cache = Cache(os.path.expanduser("~/pcpartpicker-parsed/"))
    parsed_cache["current"] = parsed_part_data


def create_json():
    all_data = {}
    cache = Cache(os.path.expanduser("~/pcpartpicker-parsed/"))
    region_data = cache["current"]
    for region in tqdm(region_data):
        part_data = region_data[region]
        dict_data = {}
        for part, data in part_data.items():
            data_to_dict = [dataclass_to_dict(item) for item in data]
            dict_data.update({part: data_to_dict})
        all_data.update({region: dict_data})
    cache = Cache(os.path.expanduser("~/pcpartpicker-json/"))
    cache["current"] = all_data


def update_html():
    cache = Cache(os.path.expanduser("~/pcpartpicker-json/"))
    all_data = cache["current"]
    dir_path = os.path.dirname(os.path.realpath(__file__))
    path = Path(os.path.join(dir_path, "docs"))
    if not path.exists():
        path.mkdir()
    for region in all_data:
        region_path = path / region
        if not region_path.exists():
            region_path.mkdir()
        for part in all_data[region]:
            part_data = all_data[region][part]
            # Check that all dicts are valid
            dataclass_data = [dataclass_from_dict(
                part_classes[part], item) for item in part_data]
            part_string = json.dumps(part_data)
            html = html_doc.format(part_string)
            file_name = part + ".html"
            with open(region_path / file_name, "w+") as file:
                file.write(html)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Scrape pcpartpicker.com.')
    parser.add_argument('--parallel', '-P', default=2, type=int,
                        metavar='N', help="Scrape up to N pages.")

    args = parser.parse_args()
    scrape_part_data(args.parallel)
    parse_part_data()
    create_json()
    update_html()
