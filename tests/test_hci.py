from pathlib import Path
import json
import struct
import tempfile
import unittest
from pactobridge.hci import import_hci, BTSNOOP_UNIX_OFFSET
from pactobridge.recording import read_events

PEER='01:02:03:04:05:06'


def connect(handle=3, address=PEER):
    data=bytes([10,0])+struct.pack('<H',handle)+bytes([0,1])+bytes.fromhex(address.replace(':',''))[::-1]+bytes(18)
    return b'\x04\x3e'+bytes([len(data)])+data


def acl(att, handle=3, boundary=2, l2cap=True):
    data=(struct.pack('<HH',len(att),4) if l2cap else b'')+att
    return b'\x02'+struct.pack('<HH',handle | (boundary<<12),len(data))+data


def snoop(entries):
    result=b'btsnoop\0'+struct.pack('>II',1,1002)
    for stamp,flags,payload in entries:
        result+=struct.pack('>IIIIQ',len(payload),len(payload),flags,0,BTSNOOP_UNIX_OFFSET+stamp)+payload
    return result


class HCITests(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root=Path(directory.name)
        self.source=self.root/'source.cfa'
        self.output=self.root/'output.jsonl'

    def run_import(self, entries):
        self.source.write_bytes(snoop(entries))
        return import_hci(self.source,self.output,PEER,notify_handle=0x12,write_handle=0x10)

    def test_target_isolation_writes_notifications_and_disconnect(self):
        stats=self.run_import([(1,3,connect()),(2,3,connect(4,'06:05:04:03:02:01')),
            (3,0,acl(b'\x52\x10\x00\xf0\xa2')),
            (4,1,acl(b'\x1b\x12\x00\xf0\xb2')),
            (5,1,acl(b'\x1b\x12\x00private',handle=4)),
            (6,0,acl(b'\x12\x13\x00\x01\x00')),
            (7,3,b'\x04\x05\x04\x00\x03\x00\x13'),
            (8,1,acl(b'\x1b\x12\x00stale'))])
        self.assertEqual(stats,{'notifications':1,'writes':1})
        rows=list(read_events(self.output))
        self.assertEqual(next(r for r in rows if r['kind']=='notification')['hex'],'f0 b2')
        self.assertNotIn('private',self.output.read_text())
        self.assertTrue(any(r.get('state')=='disconnected' for r in rows))

    def test_acl_fragmentation_and_clock_regression_preserve_source_time(self):
        att=b'\x1b\x12\x00\xf0\xb2'
        full=struct.pack('<HH',len(att),4)+att
        stats=self.run_import([(10,3,connect()),(30,1,acl(full[:6],boundary=2,l2cap=False)),
            (20,1,acl(full[6:],boundary=1,l2cap=False))])
        self.assertEqual(stats['notifications'],1)
        rows=list(read_events(self.output))
        packet=next(r for r in rows if r['kind']=='notification')
        self.assertEqual(packet['hex'],'f0 b2')
        self.assertEqual(packet['source_timestamp_us'],BTSNOOP_UNIX_OFFSET+20)

    def test_connection_handle_reuse_for_other_peer_not_imported(self):
        stats=self.run_import([(1,3,connect()),(2,3,connect(address='06:05:04:03:02:01')),
                              (3,1,acl(b'\x1b\x12\x00private'))])
        self.assertEqual(stats['notifications'],0)

    def test_malformed_input_leaves_no_partial_output(self):
        self.source.write_bytes(b'bad')
        with self.assertRaises(ValueError):
            import_hci(self.source,self.output,PEER,notify_handle=18,write_handle=16)
        self.assertFalse(self.output.exists())

    def test_no_overwrite_source_or_previous_output(self):
        self.source.write_bytes(snoop([(1,3,connect())]))
        with self.assertRaises(ValueError):
            import_hci(self.source,self.source,PEER,notify_handle=18,write_handle=16)
        self.output.write_text('keep me')
        with self.assertRaises(FileExistsError):
            import_hci(self.source,self.output,PEER,notify_handle=18,write_handle=16)
        self.assertEqual(self.output.read_text(),'keep me')
