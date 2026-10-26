#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stddef.h>
/* Independent C entropy engine: indices are PRECOMPUTED, not field/hash work. */
typedef struct {uint64_t low;uint32_t range;uint8_t cache;size_t pending,n,cap;uint8_t*out;int error;} Enc;
static void emit(Enc*e,uint8_t v){if(e->n==e->cap){e->error=1;return;}e->out[e->n++]=v;}
static void shift(Enc*e){
 if(e->low<0xFF000000ULL || e->low>0xFFFFFFFFULL){
  uint8_t t=e->cache,carry=(uint8_t)(e->low>>32);
  do{emit(e,(uint8_t)(t+carry));t=255;}while(--e->pending);
  e->cache=(uint8_t)(e->low>>24);
 }
 e->pending++;e->low=(e->low&0xFFFFFFULL)<<8;
}
__attribute__((visibility("default"))) int mtb5_entropy(const uint16_t*prior,unsigned bits,const uint32_t*indices,const uint8_t*values,size_t count,uint8_t*out,size_t cap,size_t*written,uint16_t*final){
 if(!prior||!indices||!values||!out||!written||!final||bits<10||bits>18||count>20000000||cap<1)return -1;
 size_t slots=(size_t)1<<bits;memcpy(final,prior,slots*4);Enc e={0,0xFFFFFFFFU,0,1,0,cap,out,0};
 for(size_t i=0;i<count;i++){
  if(indices[i]>=slots||values[i]>1)return -2;
  size_t k=(size_t)indices[i]*2;uint32_t a=final[k],b=final[k+1],p=(a+b)>>1;
  if(p<32)p=32;else if(p>65504)p=65504;
  uint32_t bound=(e.range>>16)*p;
  if(values[i]){e.low+=bound;e.range-=bound;a-=a>>4;b-=b>>7;}
  else{e.range=bound;a+=(65536-a)>>4;b+=(65536-b)>>7;}
  final[k]=(uint16_t)a;final[k+1]=(uint16_t)b;
  while(e.range<(1U<<24)){e.range<<=8;shift(&e);if(e.error)return -3;}
 }
 uint64_t hi=e.low+e.range-1;
 for(int k=32;k>=0;k--){uint64_t mask=((uint64_t)1<<k)-1,v=(e.low+mask)&~mask;if(v<=hi){e.low=v;break;}}
 for(int k=0;k<5;k++){shift(&e);if(e.error)return -3;}
 if(!e.n||out[0])return -4;
 memmove(out,out+1,--e.n);while(e.n && out[e.n-1]==0)e.n--;
 *written=e.n;return 0;
}
