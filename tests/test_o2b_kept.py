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

OWN_GENERATOR_HASH = "20bfbb6eb6b6901cca813308a1b7fdaf4ac512b3be3bd7b59b01b3c849d714f9"
SEEDS = (404, 55, 2121)
MOVES = {"task_id", "generator_hash"}
# 136 rows: every arm each fixture set reaches (the acme sets with their flows).
MAIN = {
    ("acme-mcp", "similarity:s0"): "3066e689023778198b2918dbcb5bc727cd6516197e41440ffd85d3a90f7d9537",
    ("acme-mcp", "similarity:s1"): "7d277dddccaf99d28544b58f125b1c55ea79d7b9cedcf7fa1142cc627741350f",
    ("acme-mcp", "similarity:s2"): "331e2a7db695e5b18a9e0d0239706ab22843c2a2915727ea21e123af897df962",
    ("acme-mcp", "similarity:s3"): "af4ce7ae465fb3c4202ec7d6d3b050ede634b87ae6e6dcd4d187bc7184a5304a",
    ("acme-mcp", "faults:f0"): "05b29c0d9f6f0db4e4dbce9a6b1ccca991e492b4dc748afc3a809cae138d980c",
    ("acme-mcp", "faults:f1"): "f022c0120fe60ef2abb6bef9789ac4527116cacce0d175e2789bcced1d28302e",
    ("acme-mcp", "faults:f2"): "d61aebf402594d96342fb708dfc13b99446c1c56509531e95486918fff654a61",
    ("acme-mcp", "faults:f4"): "bdba31ec8e7c0609b64e3ea464021a10826bb7a90c2885f710e41a333f346840",
    ("acme-mcp", "history:t0"): "8f7a2cbe3d1b1248b470549fd5bd4d98ef7441fabbb345c27334b33ba9cf866b",
    ("acme-mcp", "history:t300"): "6d36f21b1c2450f0b50c605606371e0e24ba2d4fa654e3090576e133020ff6dc",
    ("acme-mcp", "history:t600"): "5647ad9de85f873f32371eec1f5b1900bb0a00c9423c3802a2f645e6198c759a",
    ("acme-mcp", "history:t1200"): "ec87f428731131563eacef62a4f08638891a0fda9447a63d2ebe6806110f0a00",
    ("acme-mcp", "history:t2400"): "70189a1a86a0a5cb4155dccac4989a395c40ffdaec3cf756d35acfe33c8899c7",
    ("acme-mcp", "arguments:a2"): "89e9c757cd7b7c608671ded96465d468f928143ce5371d08ba7649e790215ed4",
    ("acme-mcp", "arguments:a3"): "59175325d680fdcf5867d5c9a01a7879aa06f60c8ae51aac7087194f3a7c2955",
    ("acme-mcp", "spread:p1"): "ce23d87a6a6352203afe4a60e3d8fa7d34c6dc45e5f31fa57b22600a3f76eda7",
    ("acme-mcp", "spread:p2"): "94f769235fcabeb21d6a5c587327d2c9690fe5058d9652fe536e6f8db3816f30",
    ("acme-mcp", "spread:p4"): "9ba96e0c9080d222bee1b963c6f998bdeccd5084ea55f01fd1ccffac0b1f9e2a",
    ("acme-mcp", "depth:d1"): "c2429155d23330a3ddbe24dc1596eaee4d83fe7e02c6c77054e3a543984a9047",
    ("acme-mcp", "depth:d2"): "4d16d45a17809f39cbd2a9a680086cf6cc8b3f177ff520f8a4cba64bab5a83c9",
    ("acme-mcp", "depth:d3"): "6ca725847b0577a49317c246ea2b2343dfa8a2e1f133a0a0ff3aee2be302b54f",
    ("acme-mcp", "shape:w1"): "e49c70a972c083bff9c083993fa7d11c3b20206985dd01b33ad98e90b65f8334",
    ("acme-mcp", "shape:w2"): "bcb8ae9dd4979e29f5e572c9d620bd20350d1c82844e7b16773077b74f870633",
    ("acme-mcp", "shape:w4"): "66b029bc18a9a1f61988477143e1e7cb6d0e222e89ca0784439ee0c9db3a4895",
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
    ("acme-openai", "depth:d1"): "008ba826ef3f37130b5cc79ddeb6cd0dd394fae1b7ece9815c666d323e7699d0",
    ("acme-openai", "depth:d2"): "8ff978ac9e3ca7d22071b3dbaf2a23680f9c78a10f70f5e47a50354353ef22ad",
    ("acme-openai", "shape:w1"): "95b8d5983d22e517fc6e17992808fe7b70dbaebda66b86f26beca608a559477b",
    ("acme-openai", "shape:w2"): "16e2d655da2671257663d9f8cd9d813bb97ba1c47062c3365e7ad4498988d285",
    ("acme-openai", "shape:w4"): "783d5e69c1a72653003d4c981170b2fbb75ebea8336c37110f09b143a1025311",
    ("acme-openapi-3.0", "similarity:s0"): "54d076eabfd2e9111929adba59545959aaac1d3db1ce806b93f3f9a8011a2941",
    ("acme-openapi-3.0", "similarity:s1"): "62b8c223c1c0d1dd0a130d2c8fe150532196e33d6b430aa06166bef81d7bc1d2",
    ("acme-openapi-3.0", "similarity:s2"): "19d518b1dab576158005baaaa65e5571dac66051b8efe443e601827a5c84a45b",
    ("acme-openapi-3.0", "similarity:s3"): "7377300efbe0a912c941f167e0a3f6fefa63e4ef71b10fa41e94c9c11d77cac8",
    ("acme-openapi-3.0", "faults:f0"): "65c8136a2da4c5ddba7056acd4845d0120b2cecdd8068ebde7d60d1dc15c280d",
    ("acme-openapi-3.0", "faults:f1"): "72ab038698cd612aeda2aeef9df699a2adaa9e59ee82e5f8d5f1322b4acec6cd",
    ("acme-openapi-3.0", "faults:f2"): "89c3d1f237f9a39300e94e41dfe433435c6185525613766448c4edbdc3e243f0",
    ("acme-openapi-3.0", "faults:f4"): "f1918f01a80aca673e67d113ad7888862a9389d174b494c84077736858f963f0",
    ("acme-openapi-3.0", "history:t0"): "6974078473cfd3e81e662e570485ac14fbf05ed41c3dacd0cece20e3a2df3e32",
    ("acme-openapi-3.0", "history:t300"): "528de54f6603a2acdc43d5f5e8c22bb8deb0b022423fd0a55f91181e8146abef",
    ("acme-openapi-3.0", "history:t600"): "a689e1f79e1f119127a2616f87fbddbd529aebe454c769953489100e301dc21a",
    ("acme-openapi-3.0", "history:t1200"): "9997b6fd27ae89bdb68194bd74c9637716e66d73e3c93a365233a223a9b6e080",
    ("acme-openapi-3.0", "history:t2400"): "32de3ab921cea2067714ac0e64fbc84afc83c6e8c7f90983fc7ecbcc9db76c04",
    ("acme-openapi-3.0", "arguments:a2"): "7c0f8d9af10e8b16314f37bb9edf16ad972e177b26225d68cdfa28780bfbd42e",
    ("acme-openapi-3.0", "arguments:a3"): "591a49bf8ff0ac56b283343bfd48b3ff67a26ef99054c9969e510fbe28291c4c",
    ("acme-openapi-3.0", "spread:p1"): "54ad560fca76233583e5e7870b6c82d7a29f97b5cde3889db196292a95d2633e",
    ("acme-openapi-3.0", "spread:p2"): "3a248c9741f79b88c4f16f01f4ba7ec61921cabfb241b54982248c7e80ad30df",
    ("acme-openapi-3.0", "spread:p4"): "3917da0f782c4d3ffd8e155287ce8881b234ce7f53154a0326f1a85d03f71fcf",
    ("acme-openapi-3.0", "depth:d1"): "f5965d75392ff6d838fd0340b9027a012e218a01b19ec8ce05ab9edc39251649",
    ("acme-openapi-3.0", "depth:d2"): "3b40342cfb1bf9684007328c70c3067cf4ad418d640e255558fb0ed426d185e6",
    ("acme-openapi-3.0", "depth:d3"): "d66f23d6fea34e823ad277aadf27a3d2d2766aca0ae35dc9e5046f66a22a222e",
    ("acme-openapi-3.0", "shape:w1"): "66ea531e1c77c2aaf6437b26621698c275d7162710183fadfc847ce18d1ddf1a",
    ("acme-openapi-3.0", "shape:w2"): "6238743147a82a181391250277c5d535afed5ca02390649aaec64f941b88c41a",
    ("acme-openapi-3.0", "shape:w4"): "1aee01636e14dffc3f3168337c2c086a8a468ac527676fb135887dbce44daef3",
    ("acme-openapi-3.1", "similarity:s0"): "2567275e12ce8e8bb406d7fda4cec2384698768f3dcb8c7eca6f4ce8eff3c9fa",
    ("acme-openapi-3.1", "similarity:s1"): "2ee32bb22ca9f0f95c3885e06f1c1486544436ab529031da7eaa48582525f77b",
    ("acme-openapi-3.1", "similarity:s2"): "9fbf1ee2f0e4b69c587bfddbe629d86426a320be5d18723afc1df467a6fef6ae",
    ("acme-openapi-3.1", "similarity:s3"): "7557e16a17960604b88007837bf86cee06eb075398e45e6475a4bcfdcdee1a97",
    ("acme-openapi-3.1", "faults:f0"): "a50c6bea1ca6a75fefecaac34cded8750c0ca1fe0123c7feac976f48d2ab3547",
    ("acme-openapi-3.1", "faults:f1"): "e4c69195c266610e716395500a7cf034dd52160f7b3303d54ed5055d81d424db",
    ("acme-openapi-3.1", "faults:f2"): "3a685cf69fb38d008e9ecf4ff45567f88c30d78ee24ccffdf07e0a2c8952d564",
    ("acme-openapi-3.1", "faults:f4"): "208b55c2919391f4951909f0b24d0a45a8c61185e6ac59fcfd7c7a3330aa1510",
    ("acme-openapi-3.1", "history:t0"): "f5e41eb4d9d44d572a0a610e6fe84c375607b98dec9fb27ea96132caedf18abf",
    ("acme-openapi-3.1", "history:t300"): "267bbc0a1a5e119bbbea279d9d4cbbe21818bc0604569e3f0f599ecc766a0bcb",
    ("acme-openapi-3.1", "history:t600"): "42b95f38a25bf5e801301ff651360873283df64812d20f2458f348f85ad0e321",
    ("acme-openapi-3.1", "history:t1200"): "f9b536c39be021bd3e9f15b89d9b2d93423cce1337d6ca1869a503f4dc83e8a0",
    ("acme-openapi-3.1", "history:t2400"): "da19df01a417b32b92a28124ff44bdfe09f8e2c92a0cbc0bfadb735a00580b83",
    ("acme-openapi-3.1", "arguments:a2"): "44de0660cacc9ecc4b4a9c3b441889d40698475ce96b4351feed1b1679ec6f64",
    ("acme-openapi-3.1", "arguments:a3"): "898161cd20c96ffa43d9e859b6e9fb766520286df00e32542a301465728130ac",
    ("acme-openapi-3.1", "spread:p1"): "3e26b7ea7e40df4a15c7cacd45cecebe14a9b7627f46b96afd1afd5f7754fa6a",
    ("acme-openapi-3.1", "spread:p2"): "19ff4e5be1faa0c64164334f847c94e246eb0cc6035415138eb02eb78212bf8c",
    ("acme-openapi-3.1", "spread:p4"): "70c769b7c5d203c34ca3b5f27730349a4164c666a2d5026e7f139ee1cd0e7c8a",
    ("acme-openapi-3.1", "depth:d1"): "7531cc9a8a39378bba817e9d411051f4c706fd8fb411d22d560fdd9f88bab11a",
    ("acme-openapi-3.1", "depth:d2"): "ed582ed53c93289a4450b75ff79fc2a773813c82c40a0af0f581bcefda7c7eee",
    ("acme-openapi-3.1", "depth:d3"): "bf103e0be3a25a2e106bd7f8f2db4a4f9de176dd62af386fae413a917cf68ae4",
    ("acme-openapi-3.1", "shape:w1"): "aa28bd4736a87552fda3654d709b2989c5db66baffbbc8dd2b71e534e8eba850",
    ("acme-openapi-3.1", "shape:w2"): "ff3dcf341547b443c29ab26eca5ee91f5f2a6063fb0e7d38f4e143001f976d0a",
    ("acme-openapi-3.1", "shape:w4"): "b87b5744677b0bb031c40983e922a3776a4e5f0c7a055ce36cf7e31cb272ccbc",
    ("petstore", "similarity:s0"): "90e20fe5ca6506ccd31d3a1d2880e04bb230ad1a3a61100aa774b54cb07479bb",
    ("petstore", "similarity:s1"): "b2687438a8a3bd717da5b802dbf33feaa4f53540d73e7f4ad0f2a92f919efdff",
    ("petstore", "similarity:s2"): "7eb1ad07a72fee1385a5381e05b0b58645fa994db9c1a2791b3bfd2481271f11",
    ("petstore", "similarity:s3"): "bd1ae36b346738cac13c364cb239ecc90410149ee2ba103e852707f7c5b50112",
    ("petstore", "faults:f0"): "07d2e0c08e3669d5eed17d49738871caba56e73e4f35a5c5f6dfd144401c5240",
    ("petstore", "faults:f1"): "7233a69f7be97914b1cfe694928a8be6a612a5b3b5135a457fc23bc81e96c0b3",
    ("petstore", "faults:f2"): "4c7c1f8e771ebbcd5f583ec9228cfb99750b482662a6bf95f12476e90395560b",
    ("petstore", "faults:f4"): "e802b1e7f718fe4c20b2a728359e3a59cf9b9068ec842a35fda7498a7e43a0c2",
    ("petstore", "history:t0"): "1ad1661a1c2a3bda95da3d369e8eee1bd782b9e4e39538e8eb5fb682a13cc2f8",
    ("petstore", "history:t300"): "c58d4e7a2eb79c5f4974869c4c58dee7fcc59ccb8a79b9f6d1380ff8436a8fe3",
    ("petstore", "history:t600"): "367eecc588c085da1373034d7ef260c7afd22d9e129c8034f53cf4fde2869047",
    ("petstore", "history:t1200"): "20e26fe00b2c844cdf70218a7cd00da924a0e9bec6e09fc1fd6a2fb530267d5d",
    ("petstore", "history:t2400"): "9d57d58e1de69c476316b2413cb70d30ccca4de66cf7ccd06c177f5385727bca",
    ("petstore", "block:k8"): "b084e3e1bdbee362b5c73231d6ed5d631f47b97296b4bbf4d9a524abcbd036bb",
    ("petstore", "block:k16"): "e6f660fb90d8ec02f4e883217a34e935b0c839ee8dc4ee72fc86f22ba9ae700d",
    ("petstore", "arguments:a2"): "f8034f3ff2c3ca2e63f665b410844d3deb0caacfb66f3ae1ef9c9aa49f50a21a",
    ("petstore", "arguments:a3"): "72031d5edd1459b44c0cfe3560d8797f930a303ce89885c83d5b21458f8ef1d9",
    ("petstore", "arguments:a4"): "6ef3c50b04f8f5c0ce792f634a58661b28a27ad655b387cf1b8eed73cf4661fd",
    ("petstore", "arguments:a5"): "7b694f791041bc9ffada94a2200273ba1dbce0d05b9bacdd256d883c0ad4fd78",
    ("petstore", "arguments:a6"): "a79aeb9005a08882b66a4c7b970ec2c123e57401801827119f099ccb98606e87",
    ("petstore", "spread:p1"): "713f8bed8a825f65066b52512d8e64b7be52d49b4379d29eb5461793b8c3c624",
    ("petstore", "spread:p2"): "e30253f47d235914162d73f146b5ef9edbf8df9a39b11d2d6ccc92fb3753f798",
    ("petstore", "spread:p4"): "1225f1323ed0fbb203f3415e7dfbce1104547b1eed8231de916786a5387622c3",
    ("everything", "similarity:s0"): "77ef8752411371d20cdd19980f7c6402e60f11d3448d9504fdc9cae2622e6554",
    ("everything", "similarity:s1"): "4169d229fd78c91f538d34d1395ddf137430609001bf471d1c713863f3685973",
    ("everything", "similarity:s2"): "4688d24410df3d4df47e5da67c5ffe683f1b7e9c53fc97e6f87279c488aa0c89",
    ("everything", "similarity:s3"): "bebcbedf6b03e84b44fa7776fe81c3ca51b21d8dbd983abfb0ad96225a47e617",
    ("everything", "faults:f0"): "2a81270e98bf6091ae8fdfb52d06fcda6c43aea3e2e672cf31dd8a9537ea06fb",
    ("everything", "faults:f1"): "86d1f30df8baef14be9dd81e91a107ac57fdca61657b2da01d5ffd7c7e238899",
    ("everything", "faults:f2"): "e6e4b54ba8dd424aa0c723edba23c106d1e9e44e94f6155a0e4806bb61939ad0",
    ("everything", "faults:f4"): "edf0143a919230561089d67bd019d31fe7384b3bd67fa675368b5c89a9202e7c",
    ("everything", "history:t0"): "09d64dae2b8cdc5ebeb12b1dea5ad402cd38d785979dad477f3b17f6281e523a",
    ("everything", "history:t300"): "0a63faedcefa695540e02cccd03c1f811f21d3d06496b869e2da7a5fd5dfe469",
    ("everything", "history:t600"): "2b8e7b326466bf84f07b6f8d85f01e9eb7325fcdd80f49bca920200d6e01eb0b",
    ("everything", "history:t1200"): "13b2e9f0c398febb1fdd5710ea1e7f6dd026e1b017bd060bd7ca1ec7749aaa78",
    ("everything", "history:t2400"): "ed8e8384515a5a26fbea5c09a98f010107f8c7f9d91f3363163d17f6c21501fb",
    ("everything", "block:k8"): "10f7a37e4c1d68e92a26f0193c7c4605554054b644d26984de60361ba080a069",
    ("everything", "arguments:a2"): "195998f35610699873ba743d3cc537c7ec67faf1fedcf4284b71d3ede8f822fc",
    ("everything", "spread:p1"): "f700a47f588a4679a568418eb4afd16a34b12011ccaf48583d5efb3e9e716957",
    ("everything", "spread:p2"): "cd356367c467d1052855e95a99c2dbc8da25934f508dc0161877249ea2aa5aa1",
    ("everything", "spread:p4"): "68f8cc6d1f0c659c9eb81883388bc57ecaf8f84a95d20bbe199b215af8a74087",
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
