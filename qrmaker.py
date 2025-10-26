import qrcode

# Example product URL (replace with any Amazon/Flipkart link)
# url = "https://www.amazon.in/dp/B0D12345IP" # real iphone
# url = "https://www.aptronixindia.com/iphone-15?" # fake iphone
# url = "https://amazn.in/vEHwSYq" # fake lipstick
# url = "https://www.amazon.in/Maybelline-Lipstick-Enriched-Vitamin-SuperStay/dp/B0B9R71F1V/ref=sr_1_1_sspa?" # fake lipstick
# url = "https://www.amazon.in/Philips-HL7756-00-750-Watt-Grinder/dp/B01GZSQJPA/ref=sr_1_1_sspa?"
# url = "https://www.amazon.in/Orient-Electric-Inverter-Emergency-12Watts/dp/B09X75ZYS5/ref=sr_1_2_sspa?" #bulb
# url = "https://www.amazon.in/ZEBRONICS-Launched-Rechargeable-Operation-Multicolor/dp/B0CQRNWJM2/?" 
# url = "https://www.amazon.in/ZEBRONICS-Launched-Rechargeable-Operation-Multicolor/dp/B0CQRNWJM2/?" 
url = "https://www.amazon.in/Portronics-Wireless-Bluetooth-Connectivity-Rechargeable/dp/B0BG8LZNYL/?"
# url = "https://www.amazon.in/ZEBRONICS-Launched-Rechargeable-Operation-Multicolor/dp/B0CQRNWJM2/?"
# url = "https://www.amazon.in/Dyazo-Laptop-Sleeve-Compatible-Notebooks/dp/B0BRJ86Y5V/?_encoding=UTF8&pd_rd_w=tjLoy&content-id=amzn1.sym.1014e596-2817-4003-a89c-b44bcab1a9bb&pf_rd_p=1014e596-2817-4003-a89c-b44bcab1a9bb&pf_rd_r=MPTD1725QT7FR9WKTFHE&pd_rd_wg=u8YtE&pd_rd_r=acb52cbe-4afa-4da5-a18b-111b3e3ac81a&ref_=pd_hp_d_atf_dealz_cs&th=1"

# Generate QR
qr = qrcode.QRCode(version=1, box_size=10, border=5)
qr.add_data(url)
qr.make(fit=True)

# Save as image
img = qr.make_image(fill="black", back_color="white")
img.save("amazon_iphone16.png")

print("✅ QR Code generated as amazon_iphone16.png")
