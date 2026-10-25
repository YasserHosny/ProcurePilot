// Bit-parallel anchor rejection; identical native-pixel binary comparison to privacy.py.
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
static uint64_t *bits=0;
static size_t allocated=0;
static int stride;
void prepare_frame(const uint8_t *g,int H,int W){
 stride=(W+63)/64+1;size_t size=(size_t)H*stride;
 if(size>allocated){bits=realloc(bits,size*sizeof(uint64_t));allocated=size;}
 memset(bits,0,size*sizeof(uint64_t));
 for(int y=0;y<H;y++)for(int x=0;x<W;x++)if(g[y*W+x]<185)bits[y*stride+x/64]|=UINT64_C(1)<<(x%64);
}
int glyph_matches(const uint8_t *g,int H,int W,const uint8_t *t,int h,int w,
                  const int32_t *anchors,int count,int32_t *out,int capacity){
 int found=0,columns=W-w+1;
 for(int y=0;y<=H-h;y++)for(int block=0;block*64<columns;block++){
  uint64_t candidates=UINT64_MAX;
  for(int k=0;k<count&&candidates;k++){
   int ay=anchors[3*k],ax=anchors[3*k+1],v=anchors[3*k+2],shift=ax%64;
   const uint64_t *row=bits+(y+ay)*stride+block+ax/64;
   uint64_t value=row[0]>>shift;if(shift)value|=row[1]<<(64-shift);
   candidates &= v?value:~value;
  }
  while(candidates){
   int bit=__builtin_ctzll(candidates),x=block*64+bit;candidates&=candidates-1;
   if(x>=columns)continue;
   int diff=0;
   for(int ty=0;ty<h;ty++)for(int tx=0;tx<w;tx++)diff+=((g[(y+ty)*W+x+tx]<185)!=t[ty*w+tx]);
   if((double)diff/(h*w)<.12){if(found>=capacity)return -1;out[2*found]=x;out[2*found+1]=y;found++;}
  }
 }
 return found;
}
