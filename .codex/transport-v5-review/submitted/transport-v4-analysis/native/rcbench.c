// Native replay of MTB5 encoder decisions: hashed context table (open addressing) + 16-bit two-rate
// probabilities + LZMA-style range coder. Measures the entropy-coding+context-lookup cost per event.
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
#ifndef SLOTS
#define SLOTS (1u<<15)
#endif
typedef struct{uint64_t k;uint16_t a,b;}slot;
static slot prior[SLOTS],tab[SLOTS];
static slot* get(uint64_t k){uint32_t i=(uint32_t)(k*0x9E3779B97F4A7C15ull>>49);for(;;i=(i+1)&(SLOTS-1)){if(tab[i].k==k)return &tab[i];if(!tab[i].k){tab[i].k=k;tab[i].a=tab[i].b=32768;return &tab[i];}}}
static void put(slot*t,uint64_t k,uint16_t a,uint16_t b){uint32_t i=(uint32_t)(k*0x9E3779B97F4A7C15ull>>49);while(t[i].k)i=(i+1)&(SLOTS-1);t[i].k=k;t[i].a=a;t[i].b=b;}
typedef struct{uint64_t low;uint32_t range;uint8_t cache;uint64_t csize;uint8_t*out;size_t n;}enc;
static void shiftlow(enc*e){if((uint32_t)e->low<0xFF000000u||(e->low>>32)){uint8_t c=e->low>>32;uint8_t t=e->cache;do{e->out[e->n++]=t+c;t=0xFF;}while(--e->csize);e->cache=(uint8_t)(e->low>>24);}e->csize++;e->low=(uint32_t)e->low<<8;}
static inline void ebit(enc*e,slot*s,int b){uint32_t p=(s->a+s->b)>>1;if(p<32)p=32;else if(p>65504)p=65504;uint32_t bound=(e->range>>16)*p;
 if(b){e->low+=bound;e->range-=bound;s->a-=s->a>>4;s->b-=s->b>>7;}else{e->range=bound;s->a+=(65536-s->a)>>4;s->b+=(65536-s->b)>>7;}
 while(e->range<(1u<<24)){e->range<<=8;shiftlow(e);}}
int main(int argc,char**argv){
 FILE*f=fopen(argv[1],"rb");uint32_t np;fread(&np,4,1,f);
 for(uint32_t i=0;i<np;i++){uint64_t k;uint16_t a,b;fread(&k,8,1,f);fread(&a,2,1,f);fread(&b,2,1,f);put(prior,k?k:1,a,b);}fclose(f);
 f=fopen(argv[2],"rb");uint32_t nb;fread(&nb,4,1,f);
 uint32_t*ns=malloc(nb*4),*nd=malloc(nb*4);uint64_t**keys=malloc(nb*sizeof(void*));uint8_t**bits=malloc(nb*sizeof(void*));uint64_t ev=0,dec=0;
 for(uint32_t i=0;i<nb;i++){fread(&ns[i],4,1,f);fread(&nd[i],4,1,f);keys[i]=malloc(nd[i]*8);bits[i]=malloc(nd[i]);ev+=ns[i];dec+=nd[i];
  for(uint32_t j=0;j<nd[i];j++){fread(&keys[i][j],8,1,f);fread(&bits[i][j],1,1,f);if(!keys[i][j])keys[i][j]=1;}}
 fclose(f);uint8_t*out=malloc(1<<20);size_t total=0;double best=1e9;
 for(int rep=0;rep<20;rep++){struct timespec t0,t1;clock_gettime(CLOCK_MONOTONIC,&t0);total=0;
  for(uint32_t i=0;i<nb;i++){memcpy(tab,prior,sizeof tab); // stateless: reset model to shipped prior per batch
   enc e={0,0xFFFFFFFFu,0,1,out,0};for(uint32_t j=0;j<nd[i];j++)ebit(&e,get(keys[i][j]),bits[i][j]);for(int k=0;k<5;k++)shiftlow(&e);total+=e.n;}
  clock_gettime(CLOCK_MONOTONIC,&t1);double s=(t1.tv_sec-t0.tv_sec)+(t1.tv_nsec-t0.tv_nsec)*1e-9;if(s<best)best=s;}
 // same without the per-batch 384KiB table reset (stateful mode keeps the table)
 double best2=1e9;for(int rep=0;rep<20;rep++){struct timespec t0,t1;memcpy(tab,prior,sizeof tab);clock_gettime(CLOCK_MONOTONIC,&t0);
  for(uint32_t i=0;i<nb;i++){enc e={0,0xFFFFFFFFu,0,1,out,0};for(uint32_t j=0;j<nd[i];j++)ebit(&e,get(keys[i][j]),bits[i][j]);for(int k=0;k<5;k++)shiftlow(&e);}
  clock_gettime(CLOCK_MONOTONIC,&t1);double s=(t1.tv_sec-t0.tv_sec)+(t1.tv_nsec-t0.tv_nsec)*1e-9;if(s<best2)best2=s;}
 printf("{\"events\":%llu,\"decisions\":%llu,\"decisions_per_event\":%.1f,\"bytes_unflushed_opt\":%zu,\"ns_per_decision\":%.2f,\"us_per_event_with_reset\":%.3f,\"us_per_event_no_reset\":%.3f,\"table_bytes\":%zu}\n",
  (unsigned long long)ev,(unsigned long long)dec,(double)dec/ev,total,best2*1e9/dec,best*1e6/ev,best2*1e6/ev,sizeof tab);
}
