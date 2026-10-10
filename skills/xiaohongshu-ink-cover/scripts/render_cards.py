"""Render the approved Xiaohongshu layout from a UTF-8 content specification."""
import argparse
import json
import io
import lzma
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
    cards = spec.get('cards', [])
    if not isinstance(cards, list):
        raise ValueError('cards must be a list.')
    cover = spec.get('cover')
    total = len(cards) + (1 if cover is not None else 0)
    if not total:
        raise ValueError('Provide a cover, at least one content card, or both.')
    if cover is not None:
        source = Path(cover['image'])
        if not source.is_absolute():
            source = spec_path.parent / source
        photo = Image.open(source).convert('RGB')
    if args.font == 'yahei':
        font_dir = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
        regular, bold = font_dir/'msyh.ttc', font_dir/'msyhbd.ttc'
    else:
        regular = bold = SKILL/'assets/fonts/LXGWWenKai-Regular.ttf.xz'
    font_bytes = {}
    font_cache = {}
    for path in [regular, bold]:
        if not path.is_file():
            raise FileNotFoundError(f'Required font missing: {path}')
        if path.suffix == '.xz' and path not in font_bytes:
            font_bytes[path] = lzma.decompress(path.read_bytes())

    def load_font(face, size):
        key = (face, size)
        if key not in font_cache:
            source = io.BytesIO(font_bytes[face]) if face in font_bytes else str(face)
            font_cache[key] = ImageFont.truetype(source, size)
        return font_cache[key]
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
            font = load_font(face, current)
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
        text(im,72,58,spec.get('section_label',''),32,width=760)
        text(im,900,58,f'{page}/{total}',30,width=140)
        text(im,72,1340,footer,26)
        return im, ImageDraw.Draw(im)

    def two_lines(value, field):
        if isinstance(value,str):
            value=value.split('\n')
        if not isinstance(value,list) or len(value)!=2 or not all(isinstance(v,str) and v for v in value):
            raise ValueError(f'{field} must contain exactly two nonempty lines.')
        return value

    def editorial_lines(card):
        blocks = card.get('blocks', [])
        if not isinstance(blocks, list) or not blocks:
            raise ValueError('editorial cards need at least one block.')
        for block in blocks:
            if not isinstance(block, dict) or not isinstance(block.get('text'), str) or not block['text'].strip():
                raise ValueError('Each editorial block requires nonempty text.')
            if not isinstance(block.get('label', ''), str):
                raise ValueError('Editorial block label must be a string.')
        # Wrap using measured glyph widths. Try readable sizes, never truncate.
        for size in (42, 40, 38):
            font = load_font(regular, size)
            rows = []
            y = 730
            for block in blocks:
                entries = [(block.get('label', ''), True), (block['text'], False)]
                for value, strong in entries:
                    if not value:
                        continue
                    for paragraph in value.split('\n'):
                        if not paragraph:
                            y += size // 2
                            continue
                        current = ''
                        for char in paragraph:
                            candidate = current + char
                            if font.getlength(candidate) > 928:
                                if not current:
                                    raise ValueError('An editorial glyph exceeds the safe width.')
                                rows.append((y, current, strong, size))
                                y += size + 17
                                current = char
                            else:
                                current = candidate
                        if current:
                            rows.append((y, current, strong, size))
                            y += size + 17
                y += 19
            if rows and max(row[0] + size for row in rows) <= 1230:
                return rows
        raise ValueError('Editorial content exceeds y=730..1230 at 38px. Split or edit this card; nothing was written.')

    # Render in memory so an invalid layout never leaves a partial image set.
    rendered=[]
    if cover is not None:
        im=Image.new('RGB',(W,H),'white');draw=ImageDraw.Draw(im)
        text(im,42,33,cover.get('eyebrow',''),30,width=800)
        text(im,900,33,f'1/{total}',30,width=140)
        photo_fit=ImageOps.contain(photo,(1000,562),Image.Resampling.LANCZOS)
        im.paste(photo_fit,(40+(1000-photo_fit.width)//2,95+(562-photo_fit.height)//2))
        text(im,66,706,cover.get('context',''),33)
        text(im,59,813,cover['title'],89,True,min_size=70)
        text(im,81,1000,cover['emphasis'],146,True,min_size=105)
        draw.line([(79,1193),(280,1188),(489,1192),(708,1187),(922,1190)],fill=BLACK,width=5)
        draw.line([(91,1204),(373,1201),(657,1205),(905,1200)],fill=BLACK,width=2)
        text(im,65,1241,cover.get('subtitle',''),37,True)
        text(im,65,1350,footer,25)
        rendered.append(im)
    for card_index,card in enumerate(cards,1):
        page = card_index + (1 if cover is not None else 0)
        im,draw=base(page)
        draw.ellipse((72,170,170,268),outline=BLACK,width=3)
        text(im,96,197,f'{card_index:02}',43,True)
        editorial = card.get('layout') == 'editorial'
        title = card['title']
        if editorial:
            title = title.split('\n') if isinstance(title, str) else title
            if not isinstance(title,list) or not 1 <= len(title) <= 2 or not all(isinstance(v,str) and v.strip() for v in title):
                raise ValueError('Editorial title must have one or two nonempty lines.')
        else:
            title = two_lines(title,'title')
        for index,value in enumerate(title):
            text(im,73,347+142*index,value,101,True,min_size=76)
        line(draw,79,648,838)
        if editorial:
            for y,value,strong,size in editorial_lines(card):
                text(im,76,y,value,size,strong,min_size=size,width=928)
            text(im,75,1268,card.get('takeaway',''),39,True)
            rendered.append(im)
            continue
        if card.get('layout') not in (None, 'legacy'):
            raise ValueError(f"Unknown card layout: {card.get('layout')}")
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
    columns = min(3, total)
    rows = (total + columns - 1) // columns
    sheet=Image.new('RGB',(columns*308+6,rows*412+6),'#EEEEEE')
    for index,im in enumerate(rendered):
        sheet.paste(im.resize((300,400),Image.Resampling.LANCZOS),(8+index%columns*308,8+index//columns*412))
    sheet.save(out/'preview.jpg',quality=95)
    with zipfile.ZipFile(out/'images.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for path in paths:archive.write(path,path.name)
    tag_line=' '.join('#'+tag.lstrip('#').strip() for tag in tags)
    if tag_line:tag_line+=' '
    (out/'post.txt').write_text('标题：'+post.get('title','')+'\n\n'+post.get('body','')+'\n\n'+tag_line+'\n',encoding='utf-8-sig')
    # ASCII JSON remains readable on Windows consoles with non-UTF-8 encodings.
    print(json.dumps({'output':str(out),'images':total,'size':[W,H],'font':str(regular),'postTitle':post.get('title',''),'hashtags':tag_line},ensure_ascii=True))


if __name__=='__main__':
    main()
