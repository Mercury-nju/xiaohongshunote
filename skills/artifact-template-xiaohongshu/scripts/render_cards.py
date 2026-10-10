"""Render the approved Xiaohongshu layout from a UTF-8 content specification."""
import argparse
import json
import os
from pathlib import Path
import zipfile
from PIL import Image, ImageDraw, ImageFont, ImageOps

SKILL = Path(__file__).resolve().parent.parent
W, H, BLACK = 1080, 1440, '#111111'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--font', choices=['approved', 'yahei'], default='approved')
    args = parser.parse_args()
    spec_path = args.spec.resolve()
    spec = json.loads(spec_path.read_text(encoding='utf-8-sig'))
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError('Output directory must be empty; choose a new directory.')
    cards = spec['cards']
    if len(cards) != 5:
        raise ValueError('This template requires one cover and five content cards.')
    source = Path(spec['cover']['image'])
    if not source.is_absolute():
        source = spec_path.parent / source
    photo = Image.open(source).convert('RGB')
    if args.font == 'yahei':
        font_dir = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
        regular, bold = font_dir/'msyh.ttc', font_dir/'msyhbd.ttc'
    else:
        regular = bold = SKILL/'assets/fonts/LXGWWenKai-Regular.ttf'
    for path in [regular, bold]:
        if not path.is_file():
            raise FileNotFoundError(f'Required font missing: {path}')
    footer = spec.get('footer', '')
    post = spec.get('post', {})
    tags = post.get('hashtags', [])
    if not isinstance(tags,list) or not all(isinstance(t,str) and t.lstrip('#').strip() and not any(c.isspace() for c in t.strip()) for t in tags):
        raise ValueError('post.hashtags must contain nonempty single-topic strings.')

    def text(im, x, y, value, size, strong=False, min_size=None, width=None):
        if not value:
            return
        if '\n' in value:
            raise ValueError(f'Expected one line at ({x},{y}): {value}')
        allowed = min(width or W-x-40, W-x-40)
        minimum = min_size if min_size is not None else max(22, int(size*.78))
        face = bold if strong else regular
        for current in range(size, minimum-1, -1):
            font = ImageFont.truetype(str(face), current)
            box = font.getbbox(value)
            if box[2]-box[0] <= allowed:
                break
        else:
            raise ValueError(f'Text too long; shorten or rebreak this line: {value}')
        if y+box[3]-box[1] > H-25:
            raise ValueError(f'Text exceeds the vertical safe area: {value}')
        ImageDraw.Draw(im).text((x-box[0], y-box[1]), value, font=font, fill=BLACK)

    def line(draw, x, y, width):
        draw.line([(x,y+3),(x+width//3,y),(x+width*2//3,y+2),(x+width,y-1)], fill=BLACK, width=5)

    def arrow(draw, x, y, width=95):
        draw.line((x,y,x+width,y-4), fill=BLACK, width=4)
        draw.line([(x+width-17,y-16),(x+width,y-4),(x+width-17,y+10)], fill=BLACK, width=4)

    def base(page):
        im = Image.new('RGB', (W,H), 'white')
        text(im,72,58,spec['section_label'],32,width=760)
        text(im,914,58,f'{page}/6',30)
        text(im,72,1340,footer,26)
        return im, ImageDraw.Draw(im)

    def two_lines(value, field):
        if isinstance(value,str):
            value=value.split('\n')
        if not isinstance(value,list) or len(value)!=2 or not all(isinstance(v,str) and v for v in value):
            raise ValueError(f'{field} must contain exactly two nonempty lines.')
        return value

    # Render in memory so an invalid layout never leaves a partial image set.
    rendered=[]
    im=Image.new('RGB',(W,H),'white');draw=ImageDraw.Draw(im)
    cover=spec['cover']
    text(im,42,33,cover['eyebrow'],30,width=870)
    text(im,963,33,'1/6',30)
    photo_fit=ImageOps.contain(photo,(1000,562),Image.Resampling.LANCZOS)
    im.paste(photo_fit,(40+(1000-photo_fit.width)//2,95+(562-photo_fit.height)//2))
    text(im,66,706,cover['context'],33)
    text(im,59,813,cover['title'],89,True,min_size=70)
    text(im,81,1000,cover['emphasis'],146,True,min_size=105)
    draw.line([(79,1193),(280,1188),(489,1192),(708,1187),(922,1190)],fill=BLACK,width=5)
    draw.line([(91,1204),(373,1201),(657,1205),(905,1200)],fill=BLACK,width=2)
    text(im,65,1241,cover['subtitle'],37,True)
    text(im,65,1350,footer,25)
    rendered.append(im)
    for page,card in enumerate(cards,2):
        im,draw=base(page)
        draw.ellipse((72,170,170,268),outline=BLACK,width=3)
        text(im,96,197,f'{page-1:02}',43,True)
        for index,value in enumerate(two_lines(card['title'],'title')):
            text(im,73,347+142*index,value,101,True,min_size=76)
        line(draw,79,648,838)
        text(im,76,730,card['intro'],38)
        body=two_lines(card['body'],'body')
        diagram=card.get('diagram',{});kind=diagram.get('kind')
        if kind=='comparison':
            values,labels=diagram['values'],diagram['labels']
            if len(values)!=2 or len(labels)!=2:raise ValueError('comparison needs two values and labels.')
            for index,x in enumerate([113,693]):
                text(im,x,877,values[index],91,True,width=270)
                text(im,x-2,999,labels[index],35,width=285)
            arrow(draw,461,937,119)
            text(im,111,1064,diagram.get('caption',''),28)
            for index,value in enumerate(body):text(im,76,1134+index*61,value,41)
        else:
            for index,value in enumerate(body):text(im,76,868+index*79,value,47,True)
            if kind=='steps':
                labels=diagram['labels']
                if len(labels)!=3:raise ValueError('steps needs three labels.')
                for x,label in zip([81,415,748],labels):
                    text(im,x,1100,label,40,width=210)
                    if x<748:arrow(draw,x+217,1122,67)
            elif kind=='balance':
                labels=diagram['labels']
                if len(labels)!=2:raise ValueError('balance needs two labels.')
                text(im,97,1100,labels[0],43,width=350)
                text(im,500,1104,'+',40)
                text(im,656,1100,labels[1],43,width=350)
            elif kind=='note':
                line(draw,87,1066,722)
                text(im,77,1110,diagram.get('caption',''),41)
            elif kind not in (None,'none'):
                raise ValueError(f'Unknown diagram kind: {kind}')
        text(im,75,1268,card['takeaway'],39,True)
        rendered.append(im)

    out.mkdir(parents=True,exist_ok=True)
    paths=[]
    for index,im in enumerate(rendered,1):
        path=out/f'{index:02}.png';im.save(path);paths.append(path)
    sheet=Image.new('RGB',(930,830),'#EEEEEE')
    for index,im in enumerate(rendered):
        sheet.paste(im.resize((300,400),Image.Resampling.LANCZOS),(8+index%3*308,8+index//3*412))
    sheet.save(out/'preview.jpg',quality=95)
    with zipfile.ZipFile(out/'images.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for path in paths:archive.write(path,path.name)
    tag_line=' '.join('#'+tag.lstrip('#').strip() for tag in tags)
    if tag_line:tag_line+=' '
    (out/'post.txt').write_text('标题：'+post.get('title','')+'\n\n'+post.get('body','')+'\n\n'+tag_line+'\n',encoding='utf-8-sig')
    # ASCII JSON remains readable on Windows consoles with non-UTF-8 encodings.
    print(json.dumps({'output':str(out),'images':6,'size':[W,H],'font':str(regular),'postTitle':post.get('title',''),'hashtags':tag_line},ensure_ascii=True))


if __name__=='__main__':
    main()
