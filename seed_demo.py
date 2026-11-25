"""OPTIONAL: add 4 sample properties (no photos) so you can preview the layout.
Run once:  python seed_demo.py     Delete them later from Admin > Properties."""
from database import get_db, init_db

init_db()
rows = [
    ("Sea-view 3 BHK apartment", "buy", "Apartment", 8500000, "Honnavar, Uttara Kannada", 14.2798, 74.4439, 3, 3, 1650, "Parking, Lift, Security, Sea view", 1),
    ("Modern 4 BHK villa with garden", "buy", "Villa", 21500000, "Kumta, Uttara Kannada", 14.4251, 74.4189, 4, 4, 3200, "Garden, Parking, Power backup, Terrace", 1),
    ("2 BHK family flat for rent", "rent", "Apartment", 18000, "Honnavar, Uttara Kannada", 14.2850, 74.4400, 2, 2, 1100, "Parking, Water supply, Security", 0),
    ("Residential plot near highway", "buy", "Plot / Land", 3200000, "Bhatkal, Uttara Kannada", 13.9853, 74.5550, 0, 0, 2400, "Corner plot, Clear title", 0),
]
c = get_db()
for r in rows:
    c.execute("""INSERT INTO properties (title,listing_type,property_type,price,location,lat,lng,bedrooms,bathrooms,area_sqft,amenities,featured,description)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'Sample listing for preview. Replace with your real property from the admin panel.')""",
              (r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11]))
c.commit()
print("Added 4 demo properties.")
