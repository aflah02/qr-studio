import io
from pathlib import Path
from xml.etree import ElementTree

import pytest
from PIL import Image,ImageDraw
import zxingcpp

from qr_engine import generate_qr,load_logo,normalize_url


def logo(width=160,height=160):
    im=Image.new("RGBA",(width,height),(0,0,0,0))
    d=ImageDraw.Draw(im)
    d.rounded_rectangle((3,3,width-4,height-4),radius=min(width,height)//5,fill="#007D83")
    d.ellipse((width*.35,height*.25,width*.65,height*.75),fill="white")
    stream=io.BytesIO();im.save(stream,format="PNG");return stream.getvalue()


@pytest.mark.parametrize("url",[
    "https://arxiv.org/abs/2603.11611",
    "https://github.com/aflah02/Partial_RoPE_Analysis",
    "https://huggingface.co/collections/aflah/partial-rope-analysis",
    "https://example.org/page?name=two%20words&x=1#section",
])
def test_downloads_decode_to_exact_url(url):
    result=generate_qr(url,logo(),pixels=1024)
    assert result.verified
    png=Image.open(io.BytesIO(result.png))
    assert png.size==(1024,1024)
    assert png.getpixel((0,0))==(255,255,255)
    assert round(png.info["dpi"][0])==600
    assert zxingcpp.read_barcode(png).text==url
    root=ElementTree.fromstring(result.svg)
    assert root.tag.endswith("svg")
    assert root.find(".//{http://www.w3.org/2000/svg}image") is not None
    if "&" in url:
        assert "&amp;" in result.svg


@pytest.mark.parametrize("size",[(400,70),(70,400)])
def test_wide_and_tall_logos_scan(size):
    result=generate_qr("https://example.com",logo(*size),pixels=1024)
    assert result.verified


def test_svg_logo_and_svg_download_scan():
    from cairosvg import svg2png
    svg=b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 60"><rect width="120" height="60" rx="12" fill="#007D83"/><circle cx="60" cy="30" r="18" fill="white"/></svg>'
    result=generate_qr("https://example.com/hello?x=1&y=2",svg,pixels=1024)
    assert result.verified
    output=svg2png(bytestring=result.svg.encode(),output_width=1024,output_height=1024)
    decoded=zxingcpp.read_barcode(Image.open(io.BytesIO(output)).convert("RGB"))
    assert decoded.text==result.url


def test_plain_qr_and_url_normalization():
    result=generate_qr("example.com",pixels=1024)
    assert result.url=="https://example.com"
    assert result.verified
    assert not result.has_logo
    assert "<image" not in result.svg


def test_auto_reduce_preserves_a_logo():
    result=generate_qr("https://example.com",logo(),logo_percent=28,padding_percent=30,pixels=1024)
    assert result.verified
    assert result.has_logo
    assert 6<=result.used_logo_percent<=28


@pytest.mark.parametrize("url",["", "https://", "ftp://example.com", "https://example.com:bad", "https://a.com/a b"])
def test_invalid_urls_rejected(url):
    with pytest.raises(ValueError):normalize_url(url)


def test_broken_transparent_and_linked_logos_rejected():
    with pytest.raises(ValueError):load_logo(b"not an image")
    empty=Image.new("RGBA",(30,30),(0,0,0,0));buf=io.BytesIO();empty.save(buf,format="PNG")
    with pytest.raises(ValueError,match="transparent"):load_logo(buf.getvalue())
    with pytest.raises(ValueError):
        load_logo(b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><image href="file:///etc/passwd"/></svg>')


def test_excessive_url_length_is_actionable():
    with pytest.raises(ValueError,match="too long"):
        generate_qr("https://example.org/"+"a"*1300,pixels=1024)


def test_api_upload_and_download_bundle():
    import base64
    import zipfile
    from fastapi.testclient import TestClient
    from web_app import create_app
    with TestClient(create_app()) as client:
        response=client.post('/api/generate',data={'url':'https://arxiv.org/abs/2603.11611','pixels':'1024'},files={'logo':('mark.png',logo(),'image/png')})
    assert response.status_code==200,response.text
    assert response.headers['cache-control']=='no-store'
    data=response.json()
    assert data['verified'] and data['has_logo']
    png=base64.b64decode(data['png_base64'])
    assert zxingcpp.read_barcode(Image.open(io.BytesIO(png))).text==data['url']
    archive=zipfile.ZipFile(io.BytesIO(base64.b64decode(data['zip_base64'])))
    assert archive.read(data['filename']+'.png')==png
    assert archive.read(data['filename']+'.svg').decode()==data['svg']


def test_api_svg_and_plain_qr():
    from fastapi.testclient import TestClient
    from web_app import create_app
    with TestClient(create_app()) as client:
        svg=b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80"><circle cx="40" cy="40" r="36" fill="#007D83"/></svg>'
        response=client.post('/api/generate',data={'url':'example.com','pixels':'1024'},files={'logo':('mark.svg',svg,'image/svg+xml')})
        assert response.status_code==200,response.text
        assert response.json()['verified'] and response.json()['has_logo']
        response=client.post('/api/generate',data={'url':'https://example.com/another','pixels':'1024'})
        assert response.status_code==200
        assert response.json()['verified'] and not response.json()['has_logo']
        assert response.json()['url']=='https://example.com/another'


def test_api_errors_are_actionable():
    from fastapi.testclient import TestClient
    from web_app import create_app
    with TestClient(create_app()) as client:
        assert client.post('/api/generate',data={'url':'https://'}).status_code==422
        assert client.post('/api/generate',data={'url':'https://example.com','logo_percent':99}).status_code==422
        response=client.post('/api/generate',data={'url':'https://example.com'},files={'logo':('broken.png',b'broken','image/png')})
        assert response.status_code==422
        assert 'could not be read' in response.json()['detail']
        response=client.post('/api/generate',headers={'content-length':str(7*1024*1024)},content=b'x')
        assert response.status_code==413
        assert '5 MB' in response.json()['detail']


def test_static_assets_health_and_form_ids():
    import re
    from fastapi.testclient import TestClient
    from web_app import create_app
    with TestClient(create_app()) as client:
        assert client.get('/health').json()=={'status':'ok'}
        html=client.get('/')
        assert html.status_code==200 and 'QR Studio' in html.text
        js=client.get('/static/app.js')
        assert js.status_code==200
        assert client.get('/static/style.css').status_code==200
        ids=set(re.findall(r'id="([^"]+)"',html.text))
        direct=set(re.findall(r'\$\("([^"]+)"\)',js.text))
        assert direct <= ids


def test_modal_entrypoint_loads_without_authentication():
    import runpy
    namespace=runpy.run_path(str(Path(__file__).parent/'app.py'))
    assert namespace['app'].name=='qr-studio'
    assert namespace['web'] is not None


def test_monochrome_png_is_only_black_and_white_and_still_scans():
    result=generate_qr('https://example.com',logo(),monochrome=True,pixels=1024)
    image=Image.open(io.BytesIO(result.png)).convert('RGB')
    assert result.verified and result.monochrome
    assert {color for count,color in image.getcolors(2)}=={(0,0,0),(255,255,255)}
    assert zxingcpp.read_barcode(image).text==result.url
    original=generate_qr('https://example.com',logo(),pixels=1024)
    assert not original.monochrome
    assert Image.open(io.BytesIO(original.png)).getcolors(2) is None


def test_monochrome_svg_embeds_binary_logo_and_still_scans():
    import base64
    from cairosvg import svg2png
    svg=b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="#ffcc00"/><circle cx="50" cy="50" r="30" fill="#0066cc"/></svg>'
    result=generate_qr('https://example.com',svg,monochrome=True,pixels=1024)
    root=ElementTree.fromstring(result.svg)
    embedded=root.find('.//{http://www.w3.org/2000/svg}image').get('href').split(',',1)[1]
    artwork=Image.open(io.BytesIO(base64.b64decode(embedded))).convert('RGB')
    assert {color for count,color in artwork.getcolors(2)}=={(0,0,0),(255,255,255)}
    output=Image.open(io.BytesIO(svg2png(bytestring=result.svg.encode(),output_width=1024,output_height=1024))).convert('RGB')
    assert zxingcpp.read_barcode(output).text==result.url


def test_api_explicit_no_logo_ignores_uploaded_file():
    from fastapi.testclient import TestClient
    from web_app import create_app
    with TestClient(create_app()) as client:
        result=client.post('/api/generate',data={'url':'https://example.com','logo_mode':'none','pixels':1024,'monochrome':'true'},files={'logo':('unused.png',b'not an image','image/png')})
    assert result.status_code==200,result.text
    data=result.json()
    assert data['verified'] and not data['has_logo'] and not data['monochrome']
    assert '<image' not in data['svg']


def test_api_monochrome_and_contrast():
    import base64
    from fastapi.testclient import TestClient
    from web_app import create_app
    with TestClient(create_app()) as client:
        result=client.post('/api/generate',data={'url':'https://example.com','monochrome':'true','bw_threshold':170,'pixels':1024},files={'logo':('color.png',logo(),'image/png')})
        assert result.status_code==200,result.text
        data=result.json()
        assert data['verified'] and data['monochrome']
        image=Image.open(io.BytesIO(base64.b64decode(data['png_base64'])))
        assert {color for count,color in image.getcolors(2)}=={(0,0,0),(255,255,255)}
        assert client.post('/api/generate',data={'url':'https://example.com','bw_threshold':255}).status_code==422


