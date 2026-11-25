# AG Realty

Real-estate website built with Flask, SQLite and plain HTML/CSS/JavaScript.

## Run locally

1. Install Python 3.10 or newer from python.org.
2. Open a terminal in this folder (`ag_realty/`) and run:

```
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # macOS / Linux
pip install -r requirements.txt
python app.py
```

3. Open http://127.0.0.1:5000

On first run the app creates `realestate.db` and the two admin accounts. The logins are printed in the terminal and saved in `FIRST_RUN_ADMIN_PASSWORDS.txt`. Log in at **/admin/login**, change both passwords in Admin > Settings, then delete that file.

To choose your own admin logins before first run, set `ADMIN1_EMAIL`, `ADMIN1_PASSWORD`, `ADMIN2_EMAIL`, `ADMIN2_PASSWORD` as environment variables.

Optional: `python seed_demo.py` adds 4 sample properties (no photos) so you can preview the layout. Delete them from the admin panel afterwards.

## Using the admin panel (no code editing)

- **Add property**: photos, 3D images, videos, price, Buy/Rent, type, beds, baths, area, amenities, description, availability, featured. Click the map to set the location.
- **3D / future views**: upload under "3D / future-view images" and choose the kind. The site labels them "3D Visualization", "Proposed View" or "360° Panorama" automatically.
- **Privacy**: visitors see an approximate map circle and no private address, unless you tick "Show exact location and address publicly".
- **Nearby facilities**: found automatically from OpenStreetMap (schools, hospitals, supermarkets, restaurants, banks, gyms, bus stops, metro stations, other). Add your own on the property edit page.
- **Enquiries / Users**: manage under their tabs. Properties submitted through the public Sell page wait for your approval.
- **Settings**: business phone numbers, WhatsApp number, social links (Facebook can be added later), your admin account.

Only two admin accounts exist. A database rule blocks a third.

## Structure

```
ag_realty/
├── app.py            routes and logic
├── database.py       SQLite schema, first-run setup
├── seed_demo.py      optional sample data
├── requirements.txt
├── realestate.db     created automatically
├── templates/        pages, admin/, shared macros
├── static/css, js, images, uploads
└── README.md
```

## Deploying online

- Run with `gunicorn app:app` behind HTTPS, and set `SECRET_KEY` and `HTTPS=1`.
- Use a host with a persistent disk, or set `UPLOAD_DIR` and `DATABASE_PATH` to a persistent path.
- For cloud media storage (S3, Cloudinary), change only `store_file`, `delete_file` and `media_url` in `app.py`. Full `https://` URLs are already supported in the media tables.
- For heavy traffic, move from SQLite to PostgreSQL.

## Notes

- Maps use Leaflet with OpenStreetMap tiles. Nearby places come from the public Overpass API and search from Nominatim. Both are free but rate-limited; for high traffic use a paid map provider.
- Uploads are limited to 300 MB per request.
