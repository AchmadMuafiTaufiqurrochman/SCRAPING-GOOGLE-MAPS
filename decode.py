from openlocationcode import openlocationcode as olc

# Plus code
plus_code = "HM5W+V7" 

# Harus ditambahkan area referensi (misalnya kota atau provinsi)
area_context = "Jati, Sidoarjo Regency, East Java"

# Decode dengan asumsi di Sidoarjo
decoded = olc.decode(olc.recoverNearest(plus_code, -7.45, 112.70))

print(f"Latitude: {decoded.latitudeCenter}")
print(f"Longitude: {decoded.longitudeCenter}")