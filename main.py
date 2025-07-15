import datetime
from playwright.sync_api import sync_playwright
from dataclasses import dataclass, asdict, field
import pandas as pd
import argparse
import os
import sys
from openlocationcode import openlocationcode as olc
import random
import re

@dataclass
class Business:
    """holds business data"""
    name: str = None
    address: str = None
    category: str = None
    kategori_id: str = None
    plus_code: str = None
    latitude: float = None
    longitude: float = None
    iframe_url: str = None
    jam_operasional: str = None
    size_image: str = None
    name_image: str = None
    built_year: int = None
    color: str = None
    kecamatan: str = None
    kecamatan_id: str = None
    desa: str = None
    desa_id: str = None

    
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

    def download_image(self, page, business):
        """Download and save business image if available"""
        try:
            image_locator = page.locator('//button[contains(@aria-label, "Photo of")]/img')
            if image_locator.count() > 0:
                image_url = image_locator.first.get_attribute('src')
                if image_url and business.name:
                    sanitized_name = "".join([c for c in business.name if c.isalnum() or c in (' ', '-', '_')]).rstrip()
                    sanitized_name = sanitized_name.replace('/', '_').replace('\\', '_')
                    images_dir = os.path.join(self.save_at, 'images')
                    os.makedirs(images_dir, exist_ok=True)
                    
                    response = page.request.get(image_url)
                    if response.ok:
                        file_path = os.path.join(images_dir, f"{sanitized_name}.jpg")
                        with open(file_path, 'wb') as f:
                            f.write(response.body())
                        
                        # Add these lines to store image info
                        file_size = os.path.getsize(file_path)
                        size_number = round(file_size/1024, 2)
                        business.size_image = f"{int(size_number * 100)}"  # 64.92 becomes 6492
                        business.name_image = f"{sanitized_name}.jpg"
        except Exception as e:
            print(f"Error saving image: {e}")

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

def extract_latlng_from_plus_code(plus_code: str):
    """
    Extract latitude and longitude from a plus code string.
    Returns (latitude, longitude) tuple or (None, None) if invalid.
    """
    try:
        code = plus_code.split(' ')[0].strip()
        # Jika code terlalu pendek (short code), tidak bisa didecode tanpa area
        decoded = olc.decode(olc.recoverNearest(code, -7.883063867394289, 112.53430108928096))
        # Convert to string and replace commas with periods before converting to float
        lat = float(f"{decoded.latitudeCenter:.10f}".replace(',', '.'))
        lng = float(f"{decoded.longitudeCenter:.10f}".replace(',', '.'))
        return lat, lng
    except Exception as e:
        print(f"Decode error: {e}")
        return None, None
    
def format_operational_time(time_str: str) -> str:
    """Convert time format to 24-hour format with WIB"""
    try:
        if time_str == "Open 24 hours":
            return "24 Jam"
        
        time_str = time_str.replace(' ', ' ').replace('–', 'to').strip()
        
        if 'to' in time_str.lower():
            separator = 'to' if 'to' in time_str else 'TO'
            start_str, end_str = time_str.split(separator, 1)
            
            # Handle times without AM/PM
            def parse_time(t):
                t = t.strip().replace('.', ':')
                try:
                    return datetime.datetime.strptime(t, "%I:%M %p")
                except ValueError:
                    return datetime.datetime.strptime(t, "%H:%M")

            start = parse_time(start_str)
            end = parse_time(end_str)
            
            return f"{start.strftime('%H.%M')}-{end.strftime('%H.%M')} WIB"
        return time_str
    except Exception as e:
        print(f"Time format error: {e}")
        return time_str
    
def get_kecamatan_id(kecamatan_name: str) -> str:
    """Maps kecamatan name to its ID (case-insensitive)"""
    kecamatan_mapping = {
        "junrejo": "357903",
        "batu": "357901",
        "bumiaji": "357902"
    }
    return kecamatan_mapping.get(kecamatan_name.lower(), None)

def extract_desa(address: str) -> str:
    """Extract village name from address using regex pattern"""
    if not address:
        return None
    # Pattern explanation: Capture text between comma and kecamatan mention
    # Example: "..., Sisir, Kec. Batu..." -> captures "Sisir"
    desa_match = re.search(r',\s*([^,]+?)\s*,\s*Kec\.', address, re.IGNORECASE)
    return desa_match.group(1).strip() if desa_match else None

def get_desa_id(desa_name: str) -> str:
    """Maps village name to its ID (case-insensitive)"""
    desa_mapping = {
        "dadaprejo": "3579031001",
        "beji": "3579032002",
        "junrejo": "3579032003",
        "tlekung": "3579032004",
        "mojorejo": "3579032005",
        "pendem": "3579032006",
        "torongrejo": "3579032007",
        "temas": "3579011001",
        "ngaglik": "3579011002",
        "songgokerto": "3579011003",
        "sisir": "3579011004",
        "sumberejo": "3579012005",
        "oro-oro ombo": "3579012006",
        "sidomulyo": "3579012007",
        "pesanggrahan": "3579012008",
        "punten": "3579022001",
        "gunungsari": "3579022002",
        "tulungrejo": "3579022003",
        "sumbergondo": "3579022004",
        "pandanrejo": "3579022005",
        "bumiaji": "3579022006",
        "giripurno": "3579022007",
        "bulukerto": "3579022008",
        "sumberbrantas": "3579022009"
    }
    return desa_mapping.get(desa_name.lower().strip(), None)


def get_kategori_id(category_name: str) -> str:
    """Maps category name to its ID (case-insensitive)"""
    kategori_mapping = {
        "pariwisata": "2",
        "restoran": "3",
        "warung": "3",
        "rumah makan": "3",
        "food & culinary": "3",
        "fasilitas kesehatan": "4",
        "faskes": "4",
        "tempat ibadah": "5",
        "dinas & badan opd": "6",
        "spbu": "7", 
        "pertanian": "8",
        "perkebunan": "9",
        "kebun": "9",
        "tanah kosong": "11"
    }
    return kategori_mapping.get(category_name.lower().strip(), None)

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
                    plus_code_button_xpath = '//button[contains(@class, "CsEnBe") and @data-item-id="oloc"]'
                    share_selector = '//button[@aria-label="Share" and contains(@class, "g88MCb")]'
                    embbed_map_button_selector = '//button[@aria-label="Embed a map"]'
                    input_selector = 'input.yA7sBe'
                    
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

                    if name_value := page.locator(name_attribute).inner_text():
                        business.name = name_value.strip()
                        business_list.download_image(page, business)  # Fixed: use business_list instead of self
                    else:
                        business.name = ""

                    business.category = search_for.split(' in ')[0].strip()

                    try:
                        monday_row = page.locator('//tr[.//div[text()="Monday"]]')
                        if monday_row.count() > 0:
                            time_str = monday_row.locator('td.mxowUb').first.get_attribute('aria-label').strip()
                            business.jam_operasional = format_operational_time(time_str)
                        else:
                            business.jam_operasional = None
                    except Exception as e:
                        print(f"Error getting Monday hours: {e}")
                        business.jam_operasional = None

                    if name_value := page.locator(name_attribute).inner_text():
                        business.name = name_value.strip()
                        business_list.download_image(page, business)
                    else:
                        business.name = ""

                    # Add iframe URL extraction
                    try:
                        # Use more specific selector for share button
                       
                        page.locator(share_selector).click()
                        page.wait_for_timeout(3000)  # Increased timeout
                        
                        # Click embed map button
                        page.locator(embbed_map_button_selector).click()
                        page.wait_for_timeout(3000)
                        
                        # Extract iframe URL from input field
                        page.wait_for_selector(input_selector)
                        iframe_html = page.locator(input_selector).input_value()
                        
                        # Parse src from iframe HTML
                        business.iframe_url = iframe_html
                        
                        # Close dialog
                        page.keyboard.press("Escape")
                        page.wait_for_timeout(1000) 
                    except Exception as e:
                        print(f"Error getting iframe URL: {e}")
                        business.iframe_url = None

                    business.category = search_for.split(' in ')[0].strip()
                    business.built_year = random.choice([2024, 2025, 2026])
                    
                    if business.built_year == 2024:
                        business.color = "#309898"
                    elif business.built_year == 2025:
                        business.color = "#F4631E"
                    else:
                        business.color = "#CB0404"

                    # Single check for address existence
                    if page.locator(address_xpath).count() > 0:
                        address_text = page.locator(address_xpath).all()[0].inner_text()
                        business.address = address_text
                        
                        # Single regex match for kecamatan
                        kec_match = re.search(r'kec\.\s*([^,]+)', address_text, re.IGNORECASE)
                        if kec_match:
                            kec_name = kec_match.group(1).strip()
                            business.kecamatan = kec_name
                            business.kecamatan_id = get_kecamatan_id(kec_name)
                        else:
                            business.kecamatan = None
                            business.kecamatan_id = None
                            
                        # Desa extraction
                        business.desa = extract_desa(address_text)
                        business.desa_id = get_desa_id(business.desa) if business.desa else None
                        
                    else:
                        business.address = ""
                        business.kecamatan = None
                        business.kecamatan_id = None
                        business.desa = None
                        business.desa_id = None

                    category_match = re.search(r'^.*?(\w+)\s+kota\s+batu', search_for, re.IGNORECASE)
                    if category_match:
                        raw_category = category_match.group(1).lower().strip()
                    else:
                        raw_category = search_for.split(' in ')[0].strip().lower()
                    
                    business.category = raw_category


                    business.kategori_id = get_kategori_id(raw_category)

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