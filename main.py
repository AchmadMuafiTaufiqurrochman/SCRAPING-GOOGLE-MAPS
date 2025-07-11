import datetime
from playwright.sync_api import sync_playwright
from dataclasses import dataclass, asdict, field
import pandas as pd
import argparse
import os
import sys
from openlocationcode import openlocationcode as olc


@dataclass
class Business:
    """holds business data"""
    name: str = None
    address: str = None
    category: str = None
    location: str = None
    plus_code: str = None
    latitude: float = None
    longitude: float = None
    iframe_url: str = None
    jam_operasional: str = None

    
    
    def __hash__(self):
        """Make Business hashable for duplicate detection.
        Consider businesses different if:
        - Name is different, OR
        - Same name but different non-empty contact info (domain/website/phone)
        """
        # Create a tuple of fields that must match for duplicates
        # We'll include name plus any non-empty contact info fields
        hash_fields = [self.name]
        # Only include contact info fields if they're not empty
        
        return hash(tuple(hash_fields))

@dataclass
class BusinessList:
    """holds list of Business objects,
    and save to both excel and csv
    """
    business_list: list[Business] = field(default_factory=list)
    _seen_businesses: set = field(default_factory=set, init=False)
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    save_at = os.path.join('GMaps Data', today)
    os.makedirs(save_at, exist_ok=True)

    def add_business(self, business: Business):
        """Add a business to the list if it's not a duplicate based on key attributes"""
        business_hash = hash(business)
        if business_hash not in self._seen_businesses:
            self.business_list.append(business)
            self._seen_businesses.add(business_hash)
    
    def dataframe(self):
        """transform business_list to pandas dataframe

        Returns: pandas dataframe
        """
        return pd.json_normalize(
            (asdict(business) for business in self.business_list), sep="_"
        )

    def save_to_excel(self, filename):
        """saves pandas dataframe to excel (xlsx) file

        Args:
            filename (str): filename
        """
        self.dataframe().to_excel(f"{self.save_at}/{filename}.xlsx", index=False)

    def save_to_csv(self, filename):
        """saves pandas dataframe to csv file

        Args:
            filename (str): filename
        """
        self.dataframe().to_csv(f"{self.save_at}/{filename}.csv", index=False)

def extract_coordinates_from_url(url: str) -> tuple[float, float]:
    """helper function to extract coordinates from url"""
    coordinates = url.split('/@')[-1].split('/')[0]
    # return latitude, longitude
    return float(coordinates.split(',')[0]), float(coordinates.split(',')[1])

def extract_latlng_from_plus_code(plus_code: str):
    """
    Extract latitude and longitude from a plus code string.
    Returns (latitude, longitude) tuple or (None, None) if invalid.
    """
    try:
        code = plus_code.split(' ')[0].strip()
        # Jika code terlalu pendek (short code), tidak bisa didecode tanpa area
        decoded = olc.decode(olc.recoverNearest(code, -7.883063867394289, 112.53430108928096))
        # decoded = olc.decode(code)
        return decoded.latitudeCenter, decoded.longitudeCenter
    except Exception as e:
        print(f"Decode error: {e}")
        return None, None

def main():
    # read search from arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--search", type=str)
    parser.add_argument("-t", "--total", type=int)
    args = parser.parse_args()
    
    if args.search:
        search_list = [args.search]
        
    if args.total:
        total = args.total
    else:
        # if no total is passed, we set the value to random big number
        total = 1_000_000

    if not args.search:
        search_list = []
        # read search from input.txt file
        input_file_name = 'input.txt'
        # Get the absolute path of the file in the current working directory
        input_file_path = os.path.join(os.getcwd(), input_file_name)
        # Check if the file exists
        if os.path.exists(input_file_path):
        # Open the file in read mode
            with open(input_file_path, 'r') as file:
            # Read all lines into a list
                search_list = file.readlines()
                
        if len(search_list) == 0:
            print('Error occured: You must either pass the -s search argument, or add searches to input.txt')
            sys.exit()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(locale="en-GB")

        page.goto("https://www.google.com/maps", timeout=20000)
        
        for search_for_index, search_for in enumerate(search_list):
            print(f"-----\n{search_for_index} - {search_for}".strip())

            page.locator('//input[@id="searchboxinput"]').fill(search_for)
            page.wait_for_timeout(3000)

            page.keyboard.press("Enter")
            page.wait_for_timeout(5000)

            # scrolling
            page.hover('//a[contains(@href, "https://www.google.com/maps/place")]')

            previously_counted = 0
            while True:
                page.mouse.wheel(0, 10000)
                page.wait_for_timeout(3000)

                if (
                    page.locator(
                        '//a[contains(@href, "https://www.google.com/maps/place")]'
                    ).count()
                    >= total
                ):
                    listings = page.locator(
                        '//a[contains(@href, "https://www.google.com/maps/place")]'
                    ).all()[:total]
                    listings = [listing.locator("xpath=..") for listing in listings]
                    print(f"Total Scraped: {len(listings)}")
                    break
                else:
                    if (
                        page.locator(
                            '//a[contains(@href, "https://www.google.com/maps/place")]'
                        ).count()
                        == previously_counted
                    ):
                        listings = page.locator(
                            '//a[contains(@href, "https://www.google.com/maps/place")]'
                        ).all()
                        print(f"Arrived at all available\nTotal Scraped: {len(listings)}")
                        break
                    else:
                        previously_counted = page.locator(
                            '//a[contains(@href, "https://www.google.com/maps/place")]'
                        ).count()
                        print(
                            f"Currently Scraped: ",
                            page.locator(
                                '//a[contains(@href, "https://www.google.com/maps/place")]'
                            ).count(), end='\r'
                        )

            business_list = BusinessList()

            # scraping
            for listing in listings:
                try:                        
                    listing.click()
                    page.wait_for_timeout(2000)

                    name_attribute = 'h1.DUwDvf'
                    address_xpath = '//button[@data-item-id="address"]//div[contains(@class, "fontBodyMedium")]'
                    # website_xpath = '//a[@data-item-id="authority"]//div[contains(@class, "fontBodyMedium")]'
                    # phone_number_xpath = '//button[contains(@data-item-id, "phone:tel:")]//div[contains(@class, "fontBodyMedium")]'
                    # review_count_xpath = '//div[@jsaction="pane.reviewChart.moreReviews"]//span'
                    # reviews_average_xpath = '//div[@jsaction="pane.reviewChart.moreReviews"]//div[@role="img"]' # or .fontDisplayLarge locator
                    plus_code_button_xpath = '//button[contains(@class, "CsEnBe") and @data-item-id="oloc"]'
                    plus_code_text_xpath = '//div[contains(@class, "Io6YTe") and contains(@class, "fontBodyMedium") and contains(@class, "kR99db") and contains(@class, "fdkmkc")]'                    

                    
                    business = Business()
                   
                    if name_value := page.locator(name_attribute).inner_text():
                        business.name = name_value.strip()
                    else:
                        business.name = ""

                    if page.locator(address_xpath).count() > 0:
                        business.address = page.locator(address_xpath).all()[0].inner_text()
                    else:
                        business.address = ""
                    if page.locator(plus_code_button_xpath).count() > 0:
                        aria_label = page.locator(plus_code_button_xpath).first.get_attribute("aria-label")
                        # Contoh isi aria_label: "Plus code: 4H43+43 Beji, Batu City, East Java"
                        if aria_label and "Plus code:" in aria_label:
                            plus_code_full = aria_label.replace("Plus code:", "").strip()
                            business.plus_code = plus_code_full.split(' ')[0]
                            business.latitude, business.longitude = extract_latlng_from_plus_code(business.plus_code)
                        else:
                            business.plus_code = ""
                            business.latitude, business.longitude = None, None
                    else:
                        business.plus_code = ""
                        business.latitude, business.longitude = None, None


                    business.category = search_for.split(' in ')[0].strip()
                    business.location = search_for.split(' in ')[-1].strip()
                    # business.latitude, business.longitude = extract_coordinates_from_url(page.url)
                    try:
                        monday_row = page.locator('//tr[.//div[text()="Monday"]]')
                        if monday_row.count() > 0:
                            time = monday_row.locator('td.mxowUb').first.get_attribute('aria-label').strip()
                            business.jam_operasional = time
                        else:
                            business.jam_operasional = None
                    except Exception as e:
                        print(f"Error getting Monday hours: {e}")
                        business.jam_operasional = None

                    business_list.add_business(business)
                except Exception as e:
                    print(f'Error occurred: {e}', end='\r')
            
            # output
            filename = f"{search_for}".replace(' ', '_').replace('\n', '').replace('\r', '')
            business_list.save_to_excel(filename)
            business_list.save_to_csv(filename)
        browser.close()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f'Failed err: {e}')
