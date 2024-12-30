urls = 'https://vt.tiktok.com/ZS6L15cb3/'
updated_url = '/'.join(urls.split('/', 3)[:2] + ['tnktok.com'] + urls.split('/', 3)[3:])
print(updated_url)