from openlocationcode import openlocationcode as olc

# Plus code
plus_code = "HP63+3G"

# Harus ditambahkan area referensi (misalnya kota atau provinsi)
area_context = "Pagerwojo, Sidoarjo, Indonesia"

# Decode dengan asumsi di Sidoarjo
decoded = olc.decode(plus_code)

print(f"Latitude: {decoded.latitudeCenter}")
print(f"Longitude: {decoded.longitudeCenter}")