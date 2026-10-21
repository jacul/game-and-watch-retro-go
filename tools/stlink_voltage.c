#include <libusb.h>
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>
static uint32_t le32(const unsigned char *p) { return (uint32_t)p[0] | (uint32_t)p[1]<<8 | (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24; }
int main(void) {
 libusb_context *ctx=NULL;
 int r=libusb_init(&ctx); if(r) return 1;
 libusb_device_handle *h=libusb_open_device_with_vid_pid(ctx,0x0483,0x3748);
 if(!h) { fprintf(stderr,"Cannot open ST-LINK\n"); libusb_exit(ctx); return 1; }
 r=libusb_claim_interface(h,0);
 if(r) { fprintf(stderr,"USB claim: %s\n",libusb_error_name(r)); libusb_close(h); libusb_exit(ctx); return 1; }
 libusb_clear_halt(h,0x02);
 libusb_clear_halt(h,0x81);
 unsigned char query[16]={0xF5}, mode[2]={0}; int received=0;
 r=libusb_bulk_transfer(h,0x02,query,16,&received,1000);
 if(!r) r=libusb_bulk_transfer(h,0x81,mode,2,&received,1000);
 if(r) { fprintf(stderr,"Mode query failed: %s\n",libusb_error_name(r)); libusb_release_interface(h,0); libusb_close(h); libusb_exit(ctx); return 1; }
 printf("ST-LINK mode: %u (0=DFU, 1=mass storage, 2=debug)\n",mode[0]);
 if(mode[0]==0) {
  unsigned char leave[16]={0xF3,0x07};
  r=libusb_bulk_transfer(h,0x02,leave,16,&received,1000);
  if(r) { fprintf(stderr,"Exit DFU failed: %s\n",libusb_error_name(r)); libusb_release_interface(h,0); libusb_close(h); libusb_exit(ctx); return 1; }
  usleep(100000);
 }
 int status=0;
 for(int i=0;i<5;i++) {
  unsigned char cmd[16]={0xF7}, data[8]={0}; int n=0;
  r=libusb_bulk_transfer(h,0x02,cmd,sizeof cmd,&n,1000);
  if(r || n!=16) { fprintf(stderr,"Voltage query failed: %s\n",libusb_error_name(r)); status=1; break; }
  r=libusb_bulk_transfer(h,0x81,data,sizeof data,&n,1000);
  if(r || n!=8) { fprintf(stderr,"Voltage reply failed: %s\n",libusb_error_name(r)); status=1; break; }
  uint32_t reference=le32(data), sensed=le32(data+4);
  printf("Sample %d: reference=%u sensed=%u voltage=%.4f V\n",i+1,reference,sensed,reference ? 2.4*(double)sensed/reference : 0.0);
  fflush(stdout); usleep(200000);
 }
 libusb_release_interface(h,0); libusb_close(h); libusb_exit(ctx); return status;
}
