"""Exercise production cheat decoding, mixed groups, and bounded input."""
from pathlib import Path
import subprocess,sys,tempfile
repo=Path(sys.argv[1]).resolve()
def function(text,name):
 start=text.index(name+'(');start=text.rfind('\n',0,start)+1
 end=text.index('{',start)+1;depth=1
 while depth:
  if text[end]=='{':depth+=1
  if text[end]=='}':depth-=1
  end+=1
 return text[start:end]+'\n'
port=(repo/'Core/Src/porting/nes_fceu/main_nes_fceu.c').read_text()
core=(repo/'fceumm-go/src/cheat.c').read_text()
text=r'''
#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <ctype.h>
typedef uint16_t uint16;
typedef uint8_t uint8;
typedef uint32_t uint32;
static struct {uint32 a;uint8 v;int c,type;} added[32];
static int count;
static int FCEUI_AddCheat(const char *name,uint32 a,uint8 v,int c,int type) {assert(count<32);added[count].a=a;added[count].v=v;added[count].c=c;added[count].type=type;count++;return 1;}
'''
text+=''.join(function(core,n) for n in ['GGtobin','FCEUI_DecodeGG','FCEUI_DecodePAR'])
text+=''.join(function(port,n) for n in ['checkGG','GGisvalid','cheat_hex','apply_cheat_code'])
text+=r'''
int main(void) {
 apply_cheat_code("645D:7F+645E:96+645F:98");
 assert(count==3 && added[0].a==0x645d && added[0].v==0x7f && added[0].type==0);
 assert(added[1].a==0x645e && added[1].v==0x96 && added[1].type==0);
 assert(added[2].a==0x645f && added[2].v==0x98 && added[2].type==0);
 apply_cheat_code("043F:00+SXIOPO");
 assert(count==5 && added[3].a==0x043f && added[3].type==0);
 assert(added[4].a>=0x8000 && added[4].type==1);
 apply_cheat_code("645D?01:02");
 assert(count==6 && added[5].c==1 && added[5].v==2 && added[5].type==1);
 char oversized[300];memset(oversized,'A',299);oversized[299]=0;
 apply_cheat_code(oversized);assert(count==6);
 apply_cheat_code("bad");apply_cheat_code("JJJJJJJJ");apply_cheat_code("ZZZZ:ZZ");assert(count==6);
 puts("PASS: grouped RAM codes, raw/GG mixed types, conditional reads, overlength rejection, malformed-short rejection");
}
'''
with tempfile.TemporaryDirectory(prefix='gnw-cheats-') as d:
 file=Path(d)/'test.c';file.write_text(text);exe=Path(d)/'test'
 subprocess.run(['clang','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-format','-fsanitize=address,undefined',str(file),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)
