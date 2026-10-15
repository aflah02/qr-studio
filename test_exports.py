import io
import zipfile
from xml.etree import ElementTree

import pytest
from PIL import Image
import zxingcpp
from qr_engine import generate_qr
from qr_exports import FORMATS, export_file, export_bundle, flatten_white
from test_qr_studio import logo


@pytest.mark.parametrize('style',['square','rounded','dots'])
@pytest.mark.parametrize('shape',['square','rounded','circle','hexagon','triangle'])
def test_each_style_and_shape_scans_with_colored_logo(style,shape):
    result=generate_qr('https://example.com/shape',logo(),width=1200,height=900,pixels=1024,module_style=style,canvas_shape=shape)
    assert result.width==1200 and result.height==900
    assert result.verified,[(c.label,c.passed) for c in result.checks]
    image=Image.open(io.BytesIO(result.png))
    assert image.size==(1200,900)
    assert zxingcpp.read_barcode(flatten_white(image)).text==result.url
    if shape!='square':assert image.getpixel((0,0))[3]==0


@pytest.mark.parametrize('kind',list(FORMATS))
@pytest.mark.parametrize('shape',['square','rounded','circle','hexagon','triangle'])
def test_every_export_preserves_size_and_scans(kind,shape):
    result=generate_qr('https://example.com/export',logo(),width=960,height=720,dpi=300,module_style='rounded',canvas_shape=shape,monochrome=True)
    content=export_file(result,kind)
    if kind=='svg':
        from cairosvg import svg2png
        svg=ElementTree.fromstring(content)
        assert (int(svg.get('width')),int(svg.get('height')))==(960,720)
        image=Image.open(io.BytesIO(svg2png(bytestring=content)))
    elif kind=='pdf':
        import fitz
        pdf=fitz.open(stream=content,filetype='pdf')
        assert len(pdf)==1
        assert abs(pdf[0].rect.width-960*72/300)<.1
        assert abs(pdf[0].rect.height-720*72/300)<.1
        pm=pdf[0].get_pixmap(matrix=fitz.Matrix(300/72,300/72))
        image=Image.frombytes('RGB',(pm.width,pm.height),pm.samples)
    else:
        image=Image.open(io.BytesIO(content))
        assert image.size==(960,720)
    assert zxingcpp.read_barcode(flatten_white(image)).text==result.url


def test_custom_resolution_limits_and_bundle():
    with pytest.raises(ValueError,match='36 million'):
        generate_qr('https://example.com',width=8000,height=8000)
    result=generate_qr('https://example.com',width=777,height=1023,dpi=450)
    assert Image.open(io.BytesIO(result.png)).size==(777,1023)
    assert round(Image.open(io.BytesIO(result.png)).info['dpi'][0])==450
    bundle=zipfile.ZipFile(io.BytesIO(export_bundle(result,'qr')))
    assert set(bundle.namelist())=={'qr.'+kind for kind in FORMATS}
    assert all(bundle.read(name) for name in bundle.namelist())


def test_custom_dimensions_api_and_export_routes():
    from fastapi.testclient import TestClient
    from web_app import create_app
    values={'url':'https://example.com','width':1100,'height':800,'dpi':450,'canvas_shape':'circle','module_style':'dots','logo_mode':'none'}
    with TestClient(create_app()) as client:
        response=client.post('/api/generate',data=values)
        assert response.status_code==200,response.text
        payload=response.json()
        assert (payload['width'],payload['height'],payload['dpi'])==(1100,800,450)
        assert payload['verified'] and len(payload['formats'])==8
        for kind in ['jpg','webp','svg','pdf','tiff','bmp','gif','zip']:
            response=client.post('/api/export',data={**values,'format':kind})
            assert response.status_code==200,(kind,response.text[:100])
            assert 'attachment;' in response.headers['content-disposition']
        assert client.post('/api/export',data={**values,'format':'invalid'}).status_code==422
