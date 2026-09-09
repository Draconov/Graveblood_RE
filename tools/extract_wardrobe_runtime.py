#!/usr/bin/env python3
"""Extract code-proven public-demo Wardrobe preview resources."""
from __future__ import annotations
import argparse, csv, hashlib
from pathlib import Path
ROM_BASE=0x08000000
LEVEL7_BG_BASE=0x08608A9C
OBJ_SOURCE_BASE=0x08310654
BG_PAGE_SOURCE_BIAS=0xD0C0
BG_PAGE_BYTES=0x2000
OBJ_BANK_STRIDE_UNITS=192
OBJ_CHUNK_SOURCE_UNITS=(0x24C,0x25C,0x26C,0x27C)
OBJ_CHUNK_BYTES=128
PAGES=(6,2,1,0,3,4,5)
BANKS=(15,13,12,11,6,4,5)
LABELS=("Favorite Skirt",)+("Not for demo",)*6

def _slice(data,address,size):
    off=address-ROM_BASE; end=off+size
    if off<0 or end>len(data): raise ValueError(f'ROM slice 0x{address:08X}+0x{size:X} out of range')
    return data[off:end]

def extract_runtime_assets(data):
    bg_pages=[_slice(data,LEVEL7_BG_BASE+BG_PAGE_SOURCE_BIAS+p*BG_PAGE_BYTES,BG_PAGE_BYTES) for p in PAGES]
    previews=[]
    for bank in BANKS:
        parts=[]
        for source_unit in OBJ_CHUNK_SOURCE_UNITS:
            unit=bank*OBJ_BANK_STRIDE_UNITS+source_unit
            parts.append(_slice(data,OBJ_SOURCE_BASE+unit*64,OBJ_CHUNK_BYTES))
        preview=b''.join(parts)
        if len(preview)!=512: raise AssertionError('Wardrobe preview must be 512 bytes')
        previews.append(preview)
    return {'pages':list(PAGES),'banks':list(BANKS),'labels':list(LABELS),'bg_pages':bg_pages,'preview_tiles':previews}

def _u16_values(blob): return [int.from_bytes(blob[i:i+2],'little') for i in range(0,len(blob),2)]
def _format_u16(values,indent='        ',per_line=12):
    return '\n'.join(indent+', '.join(f'0x{x:04X}' for x in values[i:i+per_line])+',' for i in range(0,len(values),per_line))

def render_c(assets):
    page_blocks=['    {\n'+_format_u16(_u16_values(b))+'\n    }' for b in assets['bg_pages']]
    preview_blocks=['    {\n'+_format_u16(_u16_values(b))+'\n    }' for b in assets['preview_tiles']]
    labels=',\n'.join(f'    "{t}"' for t in assets['labels'])
    return f'''#include <graveblood/assets.h>\n\nconst u8 gb_wardrobe_bg_page_indices[GB_WARDROBE_CHOICE_COUNT] = {{ {", ".join(str(x) for x in assets["pages"])} }};\nconst u8 gb_wardrobe_obj_banks[GB_WARDROBE_CHOICE_COUNT] = {{ {", ".join(str(x) for x in assets["banks"])} }};\n\nconst char* const gb_wardrobe_labels[GB_WARDROBE_CHOICE_COUNT] = {{\n{labels}\n}};\n\nconst u16 gb_wardrobe_bg_pages[GB_WARDROBE_CHOICE_COUNT][GB_WARDROBE_BG_PAGE_HALFWORDS] = {{\n{",\n".join(page_blocks)}\n}};\n\nconst u16 gb_wardrobe_preview_tiles[GB_WARDROBE_CHOICE_COUNT][GB_WARDROBE_PREVIEW_HALFWORDS] = {{\n{",\n".join(preview_blocks)}\n}};\n'''

def evidence_rows(assets):
    rows=[]
    for selector,(page,blob) in enumerate(zip(assets['pages'],assets['bg_pages'])):
        source=LEVEL7_BG_BASE+BG_PAGE_SOURCE_BIAS+page*BG_PAGE_BYTES
        rows.append({'kind':'bg_page','selector':str(selector),'value':str(page),'source':f'0x{source:08X}','bytes':str(len(blob)),'sha256':hashlib.sha256(blob).hexdigest(),'evidence':'0x08004F6C page*0x2000 + 0xD0C0 from Level-7 BG source'})
    for selector,(bank,blob) in enumerate(zip(assets['banks'],assets['preview_tiles'])):
        sources=[OBJ_SOURCE_BASE+(bank*OBJ_BANK_STRIDE_UNITS+unit)*64 for unit in OBJ_CHUNK_SOURCE_UNITS]
        rows.append({'kind':'preview_obj','selector':str(selector),'value':str(bank),'source':';'.join(f'0x{x:08X}' for x in sources),'bytes':str(len(blob)),'sha256':hashlib.sha256(blob).hexdigest(),'evidence':'0x08008EC6 loop; bank*Player+0x1DC(192), source offsets 0x24C..0x27C'})
    return rows

def write_outputs(root,assets):
    c=root/'reconstruction/data/wardrobe_assets.c'; csvp=root/'data/wardrobe_runtime_assets.csv'
    c.parent.mkdir(parents=True,exist_ok=True); csvp.parent.mkdir(parents=True,exist_ok=True)
    c.write_text(render_c(assets),encoding='utf-8')
    fields=['kind','selector','value','source','bytes','sha256','evidence']
    with csvp.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(evidence_rows(assets))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('rom',type=Path); ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]); a=ap.parse_args()
    write_outputs(a.root,extract_runtime_assets(a.rom.read_bytes()))
if __name__=='__main__': main()
