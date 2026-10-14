"""The own-tools tasks keep their content, and the own-tools generator's hash is recorded beside the
frozen built-in one, frozen as a test.

O2 Session A's tests pin the structure of a task on a user's own tools (the target drawn from the
writes that can be one, the stated values as JSON in the request, four named reads, the chain's
links, the controls' labels) and not its content: which target a seed draws, which values, which
reads and in what order are the build's choices, and a later change that moved them would pass
every frozen test.  As the knobs' kept files did (`tests/test_k4_kept.py` to `test_k8b_kept.py`),
this file holds a content digest per fixture set and arm, over the seeds 404, 55 and 2121 on the
eval split, strict, of every field but `task_id` and `generator_hash`, which move with any edit to
a hashed module.  It passes on the build by design; a change that moves any own task fails here.

**The own-tools generator's hash** is the second record, beside the built-in generator's frozen
`b460964dc153fab4535af3b39abd41d50198f3dcc644ae3e43ddee85544b57f9`
(`tests/test_frozen_generator.py`): the hash of `own-1` over `generator.HASHED_MODULES` as this
file was committed.  Unlike the built-in one it is not frozen: an own-tools session that edits a
hashed module updates it here and names the new hash in its record, with the digests below.  A
built-in hash that moved would fail `test_frozen_generator`, never this file; an own hash that moved
fails here, never there.

What a deliberate change updates: `OWN_GENERATOR_HASH` and the digests of the sets whose tasks moved.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json

import pytest

from poisson_tasks.knobs import arm_id
from tests.o2_support import every_arm, fixture_sets, flows_for, generator

OWN_GENERATOR_HASH = "c19b80c93353c16c967f2e8b8231ef743d9078d9c2cdddc45cc9ca9d06e9ad42"
SEEDS = (404, 55, 2121)
MOVES = {"task_id", "generator_hash"}
# 136 rows: every arm each fixture set reaches (the acme sets with their flows).
MAIN = {
    ("acme-mcp", "similarity:s0"): "4c6b36e7622437da15f6a8c3cd58dea5cea4752ac10bef9ec809f74c7797e310",
    ("acme-mcp", "similarity:s1"): "faa1a3cc618bea230d31e763e73476a9b4eb61eabe2639a3d92e68689fab15ff",
    ("acme-mcp", "similarity:s2"): "13ff0402481dd836f6d9abe337eca45690037205ca461c51599cbfebdf6b1da4",
    ("acme-mcp", "similarity:s3"): "3ef4b7d876a0d6b8047d855e03f24a07a9cd785bf76461be343ad19a34de3b3a",
    ("acme-mcp", "faults:f0"): "4b0b5f2817b178f583402741d48276843f11cb2817b35a878bf189c8e60a59f2",
    ("acme-mcp", "faults:f1"): "f1602f78f4dd1dd46a2b704fe44386eb394d5100288c6e0186a731dc217a3eb9",
    ("acme-mcp", "faults:f2"): "bd9ad4522e5cff65a38ed2c15c182b78a5dddd475fa24d89496aca5bb2e0dcfe",
    ("acme-mcp", "faults:f4"): "0b704bb7c6fa6b524f914bb0a4276dd5e9d7e2b440a16790d8f431f319731614",
    ("acme-mcp", "history:t0"): "dd9bf764957ed4ea1fc56cb8cea289d867305587b4f35b8d9b72864aa589b78e",
    ("acme-mcp", "history:t300"): "218cd51f161dc95fbddaa9a237cd5a5560e932ceeb8c5a38310bfe428e7d8ddf",
    ("acme-mcp", "history:t600"): "52df0cc15a20376edd0496c78ab573117eeb6ac1d500a0fba16b32a4d08794d5",
    ("acme-mcp", "history:t1200"): "2743f2ecdf0fdc80bcea0223ef868b1e3bcea1afb802809895fdb487f38a0c2e",
    ("acme-mcp", "history:t2400"): "3475398ea3b16ea74bad28703a864597e7573a56baed3bdad6ec0f7c7cb71eb2",
    ("acme-mcp", "arguments:a2"): "89e9c757cd7b7c608671ded96465d468f928143ce5371d08ba7649e790215ed4",
    ("acme-mcp", "arguments:a3"): "59175325d680fdcf5867d5c9a01a7879aa06f60c8ae51aac7087194f3a7c2955",
    ("acme-mcp", "spread:p1"): "aee126a4f4f618b2a6c5c4997837e8bb626c0290be9cef503bd8ac05b2eed297",
    ("acme-mcp", "spread:p2"): "6adb1c224b02e7220f11fd03ffdb335013e207019a6b76b9209bc272518f03cf",
    ("acme-mcp", "spread:p4"): "0149433e508dbf36b99c5fb4dd3a01002067db144722bc76f0e231fb12d3d0f8",
    ("acme-mcp", "depth:d1"): "0ebc7734a772d8f1fdcb67b6e4b6a44e59a0e3ea42bcb09ee3ade7e3dd7f17e8",
    ("acme-mcp", "depth:d2"): "6f625ef1ccc6477759f5b1210ab9d7401cf918bc134cc07cffe419e7f0eaa894",
    ("acme-mcp", "depth:d3"): "5d0a7fb5304a2ea57296784d86d1a79ec4517c5ef22ad44967a6dce4e42b1b84",
    ("acme-mcp", "shape:w1"): "24f30be0cf7aaa9927ac75336ebc09e9ff62dabd24cd0087a4d950d3c145b748",
    ("acme-mcp", "shape:w2"): "9323ec0d3713d1e0c1aa6f74c7c2600c0eff41a520c6068b1fd2ee4e268ebe21",
    ("acme-mcp", "shape:w4"): "d2da17efbfc4864144fde9c97a5dcf450b482ac95a59aa173b16a9956decab48",
    ("acme-openai", "similarity:s0"): "4bbb8f1031be66427c1d42472b588d47df10792ad483e82c12f0eb42ae4f4d71",
    ("acme-openai", "similarity:s1"): "31d1ddd1052d99c21a23ab16bb03c7f5e6321e44b96a9fba49613c01678d6517",
    ("acme-openai", "similarity:s2"): "d9f528cb3a470368ed88da9fb32b2393044c67811622ef464a5cd5318f2f3591",
    ("acme-openai", "similarity:s3"): "56ca0137645bdab9f6d5d8b29701f1568aee8b629da337b203ee7e695773d626",
    ("acme-openai", "faults:f0"): "7b49eac7d3cf2110f199da78d52744a0c5bc305ff93db43d267538de6ee157a6",
    ("acme-openai", "faults:f1"): "25094430cbbc4bdefe434fd9bb2ced16c1e7aba743416528d64a7ff9edcbd903",
    ("acme-openai", "faults:f2"): "0d667e4ddc0e6161b8d72a306523ab2e71f30d250f02f79e6ea9f3f6a576470d",
    ("acme-openai", "faults:f4"): "c13b66c634c1f35a8b6cee1f52d742a5031f50c70608e01e320725075529a509",
    ("acme-openai", "history:t0"): "754f30cacfa71043a83b0f8a912f79433c40be52832d273ee1274449c6851f23",
    ("acme-openai", "history:t300"): "456de8883f31e96ca12d8351f8ce4a34b42518e9acfd05bf137e02bee125dc6c",
    ("acme-openai", "history:t600"): "0266d27523a99007742023362a746450ead0b8779d4c1cfc444662fb6b818b2c",
    ("acme-openai", "history:t1200"): "0d8e3bbd237668c86c6228be1376ca9d0c69784dbb60c0da05a8be50310ad8c2",
    ("acme-openai", "history:t2400"): "5d8e75c1b9599a889361ebc3c80f1e6b64859b64698c3478218ffadb453c7021",
    ("acme-openai", "arguments:a2"): "fd387aa63768180cb21dd35b2be8218833d15f278a488509a9cc72d13bea2be7",
    ("acme-openai", "arguments:a3"): "4c1584f8c0e79188b3981bdea90b2bb9244012f22020046747a5cb6c1c57f735",
    ("acme-openai", "spread:p1"): "dd08705b59707d58d1ed349ec9f59c24265233c54449e3f1178975207b57fc12",
    ("acme-openai", "spread:p2"): "6107edb94e1ef6e9146cb3d959ee894a98d5798099589976bc1eec8bf2bb56e3",
    ("acme-openai", "spread:p4"): "9713e2e57fad10bbb97354a2d573a9521a63864d7ed2a927eef5aa5c874c1e16",
    ("acme-openai", "depth:d1"): "5777863222d733795f6cc55fe496aa2d5085f1cb2c100eab7f198a107e4093a3",
    ("acme-openai", "depth:d2"): "c78007398236791263c896e5f2a3e1bd42f99799211521c4ea58f82b07964bcd",
    ("acme-openai", "shape:w1"): "b6ec943533f50377e82a7e25f9958a2472ac9d3e7a14a4279bd84080f9488043",
    ("acme-openai", "shape:w2"): "bff79e277d6ef0d512735678b4138589a76e242f587ba047673618f3e594c5b5",
    ("acme-openai", "shape:w4"): "ec7c5291d576c397c2e4b23c4b509fe43119e7d41de8316204d3a283e86ab4cb",
    ("acme-openapi-3.0", "similarity:s0"): "535766aaa48cb007539e969031fe021b3a37d1f5995ed4ec7c2d6de87de344f3",
    ("acme-openapi-3.0", "similarity:s1"): "08bcb3bbdab4f46282e4854f083c40908613a2614f2289ee10433bbf369c46c5",
    ("acme-openapi-3.0", "similarity:s2"): "ba94b6ae63e998cf72db2c70901c2d5f14c75c5a77c35674ae01ca19c044f52f",
    ("acme-openapi-3.0", "similarity:s3"): "614159857ffc700d542cef8f397b10b6403f13126d5fb0c713aa0e435ef1accf",
    ("acme-openapi-3.0", "faults:f0"): "1469b8dd89c684e4b08e710474f6fae023855be5da7d7d2a3e5f214626b59dfe",
    ("acme-openapi-3.0", "faults:f1"): "a9c52e8d6b220fec314baf229d3e37a91f1395c33c5796a68f9a58ce80351121",
    ("acme-openapi-3.0", "faults:f2"): "b231e666bdfc9267532e7b714ca7140960ce40132e88583f19451e4cd9cee424",
    ("acme-openapi-3.0", "faults:f4"): "f867c6da6436c7a27f452c710cad408d3b454f7d0f40a290931e87217ad69fc0",
    ("acme-openapi-3.0", "history:t0"): "f4f997ab5b809addb5341539d464d1b623bfeba8c255da005ed5ca4c9389e8df",
    ("acme-openapi-3.0", "history:t300"): "abd126e1dc74ef4b1ebcd0b13fd77b1803c63e8dbba315cc75b23a0efad62c1c",
    ("acme-openapi-3.0", "history:t600"): "f65d36aaab375ebf60847d71464b237019c56c407814c3a529d1e0a41b5e6b09",
    ("acme-openapi-3.0", "history:t1200"): "c258ea03c447d43cd06e3b56d780833136bdb5a6f48a51a965881edcc2e93b22",
    ("acme-openapi-3.0", "history:t2400"): "513ac8590d609cb1dcea70d399f45025438ff6c922f5eb9acc89750e169b4c0c",
    ("acme-openapi-3.0", "arguments:a2"): "7c0f8d9af10e8b16314f37bb9edf16ad972e177b26225d68cdfa28780bfbd42e",
    ("acme-openapi-3.0", "arguments:a3"): "591a49bf8ff0ac56b283343bfd48b3ff67a26ef99054c9969e510fbe28291c4c",
    ("acme-openapi-3.0", "spread:p1"): "1cc5e3d25a99421d14ea09b8d4d913439e3417e8cc52703b1811887c6af5695f",
    ("acme-openapi-3.0", "spread:p2"): "07dc4a08a920652019289625d43204acf90c3a37a58173363c2b6964eef4b0fc",
    ("acme-openapi-3.0", "spread:p4"): "208455fc500509b012eb19c9c17b1d8830e0b82aeb9d22708d714929b904bd60",
    ("acme-openapi-3.0", "depth:d1"): "e292fb11d7d338643915bc5dfe3118f10c7421c356517ca9e3d903b94f63c75e",
    ("acme-openapi-3.0", "depth:d2"): "06108bef4fec7f9ac19a6a8ab44dce747b5a9e41f7c4c2846568daab83d80405",
    ("acme-openapi-3.0", "depth:d3"): "eedfbe655f7aff29f3379211859845c248b39413eae2252bfbe753599a15b9f1",
    ("acme-openapi-3.0", "shape:w1"): "ef3c1e3da8ecf8d87eb7085e0486c468f40c79ac60ad073cc6b9117de32ca393",
    ("acme-openapi-3.0", "shape:w2"): "35acc9a853aefc80242bb6d4cd79aeb7ecd2fade6eed351635ff3b0298cea63d",
    ("acme-openapi-3.0", "shape:w4"): "8eb7f3be546da9a73de5ad647c00538c87af674a6e2fb697148b7a2e0076d37c",
    ("acme-openapi-3.1", "similarity:s0"): "2b58edefefff39fe7ad2e3fa10527b4f2db98ae28279139635dd2a6f41ddbfd4",
    ("acme-openapi-3.1", "similarity:s1"): "dc47b02c7292cd131da16d94eb14a7e16f023286fe54f8eb83d1f8557face9ae",
    ("acme-openapi-3.1", "similarity:s2"): "978f13947b5ad117cd6d6406a353d20779c56c60f61bd03f9f66ea4bcc7134af",
    ("acme-openapi-3.1", "similarity:s3"): "5f9080fd4eb1044e4ec9bd7e1d42c69cdab0bd7a47459a1cfabaffc1018bd2f8",
    ("acme-openapi-3.1", "faults:f0"): "7be187c1fe881168737b162f731ddc0414f509a7588455a2c13a398dabe87958",
    ("acme-openapi-3.1", "faults:f1"): "2cdeaacc083707957c4b920554f0142b1fea2eb1c71491b3e381abde5919a815",
    ("acme-openapi-3.1", "faults:f2"): "2c2f6f880d70c01561cd6a8afcd1f650c60b136589a2b4608b374aab3954cdbf",
    ("acme-openapi-3.1", "faults:f4"): "bdd960e8e7102c9bad7a11b5a44dbff7ce128f173056a1f8b83edb94351c3dee",
    ("acme-openapi-3.1", "history:t0"): "9f276f48681f3fac17dbc32106a8b3816fe50251a1fd513962eac7315afd6a61",
    ("acme-openapi-3.1", "history:t300"): "ac6a738ea4b8092adfc565a0514c8c7ed4824ef8e43465697d8ae0283877c6bf",
    ("acme-openapi-3.1", "history:t600"): "0e0e1bb74d7135a02ed8d9fb3ce986f778fc18155e7ee44239551c48800a906f",
    ("acme-openapi-3.1", "history:t1200"): "8675ec74a8e540b80bc30c23dee24a23912e362b434bf8199963ff7c6951ca54",
    ("acme-openapi-3.1", "history:t2400"): "56fd305ec23718b0bbbae859ffd5ed643e683b6cf3a20a2c7335c4d815a23c76",
    ("acme-openapi-3.1", "arguments:a2"): "44de0660cacc9ecc4b4a9c3b441889d40698475ce96b4351feed1b1679ec6f64",
    ("acme-openapi-3.1", "arguments:a3"): "898161cd20c96ffa43d9e859b6e9fb766520286df00e32542a301465728130ac",
    ("acme-openapi-3.1", "spread:p1"): "69c22962e659ad02341460bfe87154875822fa740b8424135e79f2ef71b7c6b3",
    ("acme-openapi-3.1", "spread:p2"): "c3485947df36e9e8ed8a7f61900f5bdce5335a614a2ae02ab6b1b4ac9eac75d3",
    ("acme-openapi-3.1", "spread:p4"): "18616d0e79df1ec894dbfce4678b591af283dc06da86054372ebfc4a3b83502a",
    ("acme-openapi-3.1", "depth:d1"): "90b88d4dc8c8f0a539bad6d0dba4b8a9fa4e7d22433b98e19f15816a1341a13d",
    ("acme-openapi-3.1", "depth:d2"): "c06708819bd9b5fae048721649f36a856cdbafbdff4aa66a5758d1f51bf834dc",
    ("acme-openapi-3.1", "depth:d3"): "b9324951d771c777859a0fbbfdefca08f527414351f026c9a6b8e5e3be3cfb9c",
    ("acme-openapi-3.1", "shape:w1"): "f247312208497bd70251348ff4e2331111b7c4494ef7a67885a880e63e20235e",
    ("acme-openapi-3.1", "shape:w2"): "9c40c12187e625674fba398a008277748237d6aaf69c0824c96ec422f6e066d7",
    ("acme-openapi-3.1", "shape:w4"): "2b97d3e523452b7b1eac1a5c341e928d4261840548b140aeb6fdf342a6dbfbdd",
    ("petstore", "similarity:s0"): "0edd1aa8d31cf759c2e08f0b97a03234ec634e5b416c5d9e7aa48c589f169fcd",
    ("petstore", "similarity:s1"): "60a3c62521055a84df096bd82fa7cf2cc4b5069707939156040633252d0f6f1c",
    ("petstore", "similarity:s2"): "7aa46088b894a3246b1c38eda2579537558e9e786e0a652206b08a3a8104b451",
    ("petstore", "similarity:s3"): "79c0c9bde35801a82fb737b28f19408e53d51cff96c0de2f97744ccaf2ed3242",
    ("petstore", "faults:f0"): "887026ce8f39d373ea7e3c6f706f5d3863754ba33db9bb43968b22e08f51e7c2",
    ("petstore", "faults:f1"): "126c312ca02cc8a4fb85b456c77e135b86666217efbaa32b786579174ee177ed",
    ("petstore", "faults:f2"): "16291b8b68fbee31c928a64f4150c40a28aa6788fd49b8df7db7e5244db4ac39",
    ("petstore", "faults:f4"): "5f22f192f0586afb41d46defbd775392d9b73ae70cbfbc7fcdfaf2c682cb303c",
    ("petstore", "history:t0"): "de6feb8665caf628523fc835b955ceb70364a93e0d13a3072765a0891ac7b411",
    ("petstore", "history:t300"): "2bdd356688e56388646f7191e0ec4dffff67e9e9ac123809e06272cf29fca440",
    ("petstore", "history:t600"): "6ecec4638a245c74a99bddba4f015ea08e623c435b0f77f7db10748712f0bea1",
    ("petstore", "history:t1200"): "2c2ac267bf0832cfb14619ebdf064955b4e7ebce8622878585e4d6cfd8c4961f",
    ("petstore", "history:t2400"): "3ee2cfeecbfc6cc5fcc67edd18da7b6103146436e31b9bee42a6cbec9a2e245a",
    ("petstore", "block:k8"): "43779b59284eec1a29dca55b2dea398d554ee31a3e03ba9eb2617b3b47175144",
    ("petstore", "block:k16"): "a2b858512e9fa2bacdb49f35ecb7892a9ec13f7a664694b5497e3e9a21119957",
    ("petstore", "arguments:a2"): "f8034f3ff2c3ca2e63f665b410844d3deb0caacfb66f3ae1ef9c9aa49f50a21a",
    ("petstore", "arguments:a3"): "72031d5edd1459b44c0cfe3560d8797f930a303ce89885c83d5b21458f8ef1d9",
    ("petstore", "arguments:a4"): "6ef3c50b04f8f5c0ce792f634a58661b28a27ad655b387cf1b8eed73cf4661fd",
    ("petstore", "arguments:a5"): "7b694f791041bc9ffada94a2200273ba1dbce0d05b9bacdd256d883c0ad4fd78",
    ("petstore", "arguments:a6"): "a79aeb9005a08882b66a4c7b970ec2c123e57401801827119f099ccb98606e87",
    ("petstore", "spread:p1"): "8dcbefbeba8f15f75edad04d4fcba39a56a30f5087036971baf45ea1a5ed9e3d",
    ("petstore", "spread:p2"): "015cd2c1dbc8a422a8a871ee0ef87d2dec9d76b0579f068a63c7ae1cd3c39593",
    ("petstore", "spread:p4"): "0edc87dda36e2937322c5c007dee3fd8b58d548034fd550e6516f0b6d50b6c5b",
    ("everything", "similarity:s0"): "cddc5977fa2c2647eb5d4065b43fbbe5e8c85fa8af3a1559622ac0abbfa1af59",
    ("everything", "similarity:s1"): "5a0b48896d28a06bd8cf25cbd0b59e0b2f5b52e2ae3d201e1302466fafdccfaa",
    ("everything", "similarity:s2"): "2da961c8598804fb021a17f32aa2cd9e09acae9be5ad4b6e2dfd5399f96789c0",
    ("everything", "similarity:s3"): "229300144084073af674ee0399d698426470db50b1bd2cafe6e59c8106b6f3ec",
    ("everything", "faults:f0"): "a43b52814c8e96c74a9adcf42a59941a0e149c42513911167df0f02c42b05c3e",
    ("everything", "faults:f1"): "83fbfdf6a667e84b68f0e4f8d1cbbef762cb2297c4eddc609201a617c19ee3ee",
    ("everything", "faults:f2"): "f52c8b1cf6f854d0caeeccd968bea15f5211f0048d08de5008658692c05ca89b",
    ("everything", "faults:f4"): "14ed8f1aabec9f7b05b153f96b539d448d871b6bb92af52f9595add3115dc303",
    ("everything", "history:t0"): "0c2205c54fd41ad56560dbbe9369bf5d704b136c2af038ec9e33b409c9483584",
    ("everything", "history:t300"): "e1f049a6a3750655ff7fff9b67537fba045030c6074355c969130eb85a84bf7b",
    ("everything", "history:t600"): "61c9e49aa7030a19e38883f5245e8978ed647d973e869bb5dd3a5b43e87660c9",
    ("everything", "history:t1200"): "9d6c450b42879f0c4d30912d6b2c44064dc55e82d10269ab3cfa3fc510ae653c",
    ("everything", "history:t2400"): "52b0a3d79adc3e85a559feb5bf41347447d60153761a3cb3b0d127d9fb8245a4",
    ("everything", "block:k8"): "0e597762ce66ca36738fbe7ff2d2dd942be01df067cf6f76c60b0ecb1db00f03",
    ("everything", "arguments:a2"): "195998f35610699873ba743d3cc537c7ec67faf1fedcf4284b71d3ede8f822fc",
    ("everything", "spread:p1"): "fa0aed5e7ec45478c4ce1f45f48a82d8d4c3f56b3dbf4bbe27cf3c55d6b8560f",
    ("everything", "spread:p2"): "d688bd64e2ece3099d0e5ab37ff5132a3de1fdb2e3dfbc8424fbf2d684dda000",
    ("everything", "spread:p4"): "41c3a60f0d91f96576f9210bd6a4e4677e62de6e400bb45cb891417816d9f022",
}


def plain(value: object) -> object:
    return list(value)  # type: ignore[call-overload]


def test_the_own_tools_generator_hash_is_the_recorded_one() -> None:
    assert generator().generator_hash() == OWN_GENERATOR_HASH, (
        "the own-tools generator's hash moved: a hashed module changed; record the new hash here"
        " and in the session's record, with the digests of the tasks that moved"
    )


@pytest.mark.parametrize(("label", "arm"), sorted(MAIN))
def test_the_own_tools_tasks_keep_their_content(label: str, arm: str) -> None:
    toolset, flows = fixture_sets()[label], flows_for(label)
    (spec,) = [s for s in every_arm(toolset, flows) if arm_id(s) == arm]
    digest = hashlib.sha256()
    for seed in SEEDS:
        bundle = generator().generate(toolset, spec, seed, flows=flows)
        content = {
            field.name: getattr(bundle, field.name)
            for field in dataclasses.fields(bundle)
            if field.name not in MOVES
        }
        digest.update(json.dumps(content, sort_keys=True, separators=(",", ":"), default=plain).encode())
        digest.update(b"\n")
    assert digest.hexdigest() == MAIN[(label, arm)], (
        f"the own-tools tasks of {label} {arm} moved: a deliberate change updates this digest"
    )
