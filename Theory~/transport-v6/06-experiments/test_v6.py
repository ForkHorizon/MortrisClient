import copy, json, math, random, struct, unittest, uuid, zlib
from codec import *
from support import make, rebatch, drift

class V6Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ds = rebatch(make('base', 101, 1), 100)
        cls.schema = Schema.train(rebatch(make('base', 202, 1), 100))

    def check(self, batch, origin, **opts):
        client, server = Aliases(), Aliases()
        payload = client.register(origin, batch)
        server.accept(payload)
        f = encode(self.schema, client, origin, batch, **opts)
        got = decode(self.schema, server, f, authorized_origin=origin)
        want = opts.get('source', render(origin, batch, opts.get('preserve_ids', False)))
        self.assertEqual(got, want)
        return f, client, server

    def test_all_profiles(self):
        for profile in ('base', 'rich', 'alt', 'drift'):
            ds = drift(1733, 1, 70) if profile == 'drift' else rebatch(make(profile, 1729, 1), 100)
            for inst, batches in ds:
                for b in batches[:3]:
                    for replay in (False, True):
                        self.check(b, inst.install_id, replay=replay, preserve_ids=True)

    def test_options_and_cold_alias(self):
        inst, batches = self.ds[0]
        for replay in (False, True):
            for ids in (False, True):
                for masks in (False, True):
                    f, client, server = self.check(batches[0], inst.install_id, replay=replay, preserve_ids=ids, masks=masks)
                    with self.assertRaises(ValueError):
                        decode(self.schema, Aliases(), f, authorized_origin=inst.install_id)
                    with self.assertRaises(ValueError):
                        decode(self.schema, server, f, authorized_origin=str(uuid.uuid4()))
                    with self.assertRaises(ValueError):
                        decode(Schema([]), server, f, authorized_origin=inst.install_id)

    def test_types_and_unknown_shapes(self):
        inst, batches = self.ds[0]
        b = copy.deepcopy(batches[0][:8])
        values = [None, False, -0.0, 1.7976931348623157e308, (1 << 64)-1, -(1 << 63), '🙂\ud800', Decimal('0.00500')]
        for i, value in enumerate(values):
            b[i]['name'] = 'new_event'
            b[i]['properties'] = {'new_field': value, 'app_version': 120.0, 'wave_attempt_id': 'different'}
        self.check(b, inst.install_id)
        f, a, _ = self.check(b, inst.install_id)
        raw = encode_raw(self.schema, a, inst.install_id, b)
        _, restored = decode_raw(self.schema, a, raw, len(b), 0)
        for original, actual in zip(b, restored):
            x, y = original['properties']['new_field'], actual['properties']['new_field']
            self.assertIs(type(x), type(y))
            if type(x) is float:
                self.assertEqual(struct.pack('<d', x), struct.pack('<d', y))
            else:
                self.assertEqual(x, y)

    def test_literal_escape(self):
        inst, batches = self.ds[0]
        b = batches[0][:3]
        source = render(inst.install_id, b).replace(b'"schema_version":1', b'"schema_version" : 1')
        source = source.replace(b'"sent_at_client":', b'"sent_at_client" :')
        self.check(b, inst.install_id, source=source)

    def test_binary_schema_and_lz4(self):
        from schema_tools import pack_schema, unpack_schema
        encoded = pack_schema(self.schema)
        self.assertEqual(unpack_schema(encoded).data, self.schema.data)
        with self.assertRaises(ValueError):
            unpack_schema(encoded+b'\x00')
        inst, batches = self.ds[0]
        self.check(batches[0], inst.install_id, lz4=True, replay=True, preserve_ids=True)

    def test_semantic_limits(self):
        inst, batches = self.ds[0]
        b = copy.deepcopy(batches[0][:3])
        b[0]['name'] = 'invalid__name'
        aliases = Aliases();aliases.register(inst.install_id, b)
        f = encode(self.schema, aliases, inst.install_id, b)
        with self.assertRaises(ValueError):
            decode(self.schema, aliases, f, authorized_origin=inst.install_id)
        b = batches[0][:3]
        source = json.loads(render(inst.install_id, b))
        source['sent_at_client'] = 7
        f = encode(self.schema, aliases, inst.install_id, b, source=dump(source))
        with self.assertRaises(ValueError):
            decode(self.schema, aliases, f, authorized_origin=inst.install_id)

    def test_hash_escape(self):
        inst, batches = self.ds[0]
        b = copy.deepcopy(batches[0])
        for e in b:
            if 'placed_state_hash' in e['properties']:
                e['properties']['placed_state_hash'] = '0'*64
        self.check(b, inst.install_id, replay=True)
        b[0]['properties']['placed_state_hash'] = 'ab'*40
        with self.assertRaises(ValueError):
            self.check(b, inst.install_id, replay=True)

    def test_integers(self):
        rng = random.Random(483)
        cases = [[], [0], [-(1 << 63), (1 << 63)-1], [15]*500, list(range(500))]
        cases += [[rng.randint(-1000000, 1000000) for _ in range(rng.randint(1, 500))] for _ in range(100)]
        for xs in cases:
            r = Reader(integers(xs))
            self.assertEqual(xs, readintegers(r, len(xs)))
            r.end()

    def test_fixed_point_exactness(self):
        for t, fmt in ((core.T_F32, '<f'), (core.T_F64, '<d')):
            for values in ([1.25]*20, [-0.0]*20, [0.005, 0.1, -2.51, 100.0]):
                values = [struct.unpack(fmt, struct.pack(fmt, v))[0] for v in values]
                encoded = enc_values(t, values)
                r = Reader(encoded)
                restored = dec_values(r, t, len(values))
                self.assertEqual([struct.pack(fmt, v) for v in values], [struct.pack(fmt, v) for v in restored])
                r.end()
                if values == [1.25]*20:
                    self.assertEqual(encoded[0], 1)

    def test_mutations(self):
        inst, batches = self.ds[0]
        f, _, server = self.check(batches[0], inst.install_id)
        rng = random.Random(631)
        rejected = 0
        for ix in range(1000):
            mutated = bytearray(f)
            if ix % 3 == 0:
                mutated = mutated[:rng.randrange(len(f))]
            elif ix % 3 == 1:
                mutated[rng.randrange(len(f))] ^= 1 << rng.randrange(8)
            else:
                mutated += b'\x00'
            try:
                decode(self.schema, server, bytes(mutated), authorized_origin=inst.install_id)
            except ValueError:
                rejected += 1
        self.assertEqual(rejected, 1000)
        # With recomputed CRC exercise the bounded parser rather than just CRC detection.
        for body in (b'M6\xff\x00'+f[4:-4], f[:-4]+b'junk'):
            bad = body+struct.pack('<I', zlib.crc32(body))
            with self.assertRaises(ValueError):
                decode(self.schema, server, bad, authorized_origin=inst.install_id)

    def test_alias_transaction(self):
        client, server = Aliases(), Aliases()
        inst, batches = self.ds[0]
        p = client.register(inst.install_id, batches[0])
        server.accept(p)
        before = list(server.records)
        with self.assertRaises(ValueError):
            server.accept(p)
        self.assertEqual(server.records, before)
        self.assertEqual(client.register(inst.install_id, batches[0]), b'')

    def test_alias_epoch_restart(self):
        inst, batches = self.ds[0]
        f, client, server = self.check(batches[0], inst.install_id)
        stale = Aliases(epoch=b'newepoch')
        stale.records = list(server.records)
        stale.ids = dict(server.ids)
        with self.assertRaises(ValueError):
            decode(self.schema, stale, f, authorized_origin=inst.install_id)
        with self.assertRaises(ValueError):
            stale.accept(client.epoch+b'invalid')

if __name__ == '__main__':
    unittest.main()
