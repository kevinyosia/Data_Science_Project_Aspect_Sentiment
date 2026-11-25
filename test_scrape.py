from google_play_scraper import reviews
hasil, token = reviews("com.mobile.legends", lang="id", country="id", count=10)
print(len(hasil), hasil[0]["content"])