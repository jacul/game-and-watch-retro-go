"""Install a prepared Zelda migration after verifying the exact captured baseline."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from .common import hashes, make_connection, require

BASE=0x90000000
SIZE=4194304

def read_checked(directory,name,manifest):
    data=(directory/name).read_bytes()
    item=manifest[name]
    require(len(data)==item.get('size',len(data)) and hashlib.sha256(data).hexdigest()==item['sha256'], 'File hash mismatch: '+name)
    return data

def prepare(package,baseline):
    p=json.loads((package/'manifest.json').read_text())
    b=json.loads((baseline/'manifest.json').read_text())
    target_ext=read_checked(package,'external-with-saves.bin',p)
    target_int=read_checked(package,'gw_retro_go_intflash.bin',p)
    migration=json.loads(read_checked(package,'save-migration.json',p))
    layout=json.loads(read_checked(package,'layout.json',p))
    tail=layout['journal_start']
    require(layout['flash_size']==SIZE and tail%4096==0 and 0<tail<layout['journal_end']<SIZE-4096,
            'Unexpected Zelda journal layout')
    require(layout['games'], 'Expected compiled games')
    cursor=tail
    for game in layout['games']:
        size=game['battery_size'];slot=((28+size+4095)//4096)*4096
        if size:
            require(size in (8192,32768) and game['slot_size']==slot and game['battery_offset']==cursor,
                    'Invalid per-game journal layout')
            cursor+=2*slot
        else:
            require(not game['cartridge_battery'] and game['slot_size']==0 and game['battery_offset'] is None,
                    'Missing battery reservation')
        require(layout['journal_end']<=game['snapshot_offset'] and
                game['snapshot_offset']+game['snapshot_size']<=SIZE-4096, 'Invalid snapshot layout')
    require(cursor==layout['journal_end'], 'Journal allocation differs')
    require(migration and len({(g['system'],g['title']) for g in migration})==len(migration), 'Invalid save migration list')
    for item in migration:
        require(any(all(item[key]==game[key] for key in ('system','title','battery_offset','battery_size','rom_crc32','snapshot_offset'))
                    for game in layout['games']), 'Migration differs from game layout')
    old_ext=read_checked(baseline,'external.bin',b)
    old_int=read_checked(baseline,'bank1.bin',b)
    if 'baseline.json' in p:
        source=json.loads(read_checked(package,'baseline.json',p))
        require(source['external_sha256']==hashlib.sha256(old_ext).hexdigest() and
                source['internal_sha256']==hashlib.sha256(old_int).hexdigest(), 'Package migration source differs from baseline')
    require(len(target_ext)==len(old_ext)==SIZE,'Expected 4 MiB Zelda images')
    require(8<=len(target_int)<=262144 and len(old_int)==262144,'Unexpected internal image size')
    return target_ext,target_int,old_ext,old_int,tail

def install(backend,device,images,backup):
    target_ext,target_int,old_ext,old_int,tail_offset=images
    opened=False
    try:
        backend.open();opened=True;backend.set_frequency(100000)
        require(device._get_status()=='IDLE','Start the verified RAM helper in a separate process first')
        device._gnwmanager_started=True
        require(device.external_flash_size==SIZE,'Expected original 4 MiB Zelda flash')
        require(device.external_flash_block_size==4096,'Expected 4 KiB erase sectors')
        actual=device.read_memory(0x08000000,262144)
        require(actual==old_int,'Current firmware differs from captured Zelda baseline')
        require(device.read_hashes(0,SIZE)==hashes(old_ext),'Device data changed after backup; capture fresh saves before installing')
        backup.mkdir(parents=True,exist_ok=False)
        (backup/'bank1-before.bin').write_bytes(actual)
        (backup/'external-before.bin').write_bytes(old_ext)
        meta={'status':'writing','baseline_verified':True,'external_before_sha256':hashlib.sha256(old_ext).hexdigest()}
        (backup/'installation.json').write_text(json.dumps(meta,indent=2)+'\n')
        print('Exact Zelda baseline verified. Installing prepared firmware and migrated saves.',flush=True)
        device.flash(0,0,target_ext,progress=True,desc='Zelda firmware and saves')
        device.flash(1,0,target_int)
        require(device.read_hashes(0,SIZE)==hashes(target_ext),'External flash verification failed')
        require(device.read_memory(0x08000000,len(target_int))==target_int,'Internal flash verification failed')
        # Verify every journal, snapshot, and settings byte by direct read.
        require(device.read_memory(BASE+tail_offset,SIZE-tail_offset)==target_ext[tail_offset:], 'Migrated saves or settings readback differs')
        meta.update(status='verified',installed_at_utc=datetime.now(timezone.utc).isoformat(),
                    external_after_sha256=hashlib.sha256(target_ext).hexdigest(),
                    internal_after_sha256=hashlib.sha256(target_int).hexdigest(),runtime_test='pending')
        (backup/'installation.json').write_text(json.dumps(meta,indent=2)+'\n')
        device.reset()
        print('Firmware, journals, snapshots, and settings verified. Zelda restarted.',flush=True)
        return meta
    finally:
        if opened:backend.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('package','baseline','backup'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--helper-running',action='store_true',required=True)
    args=parser.parse_args();images=prepare(args.package,args.baseline)
    backend,device=make_connection();install(backend,device,images,args.backup)

if __name__=='__main__':main()
