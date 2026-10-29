"""The own-tools tasks keep their content, and the own-tools generator's hash is recorded beside the
frozen built-in one, frozen as a test.

The frozen `test_o2_*` tests pin the structure of a task on a user's own tools (the target drawn
from the writes that can be one, the stated values as JSON in the request, four named reads, the
chain's links, the controls' labels) and not its content: which target a seed draws, which values,
which reads and in what order are the build's choices, and a later change that moved them would pass
every frozen test.  As the knobs' kept files did (`tests/test_k4_kept.py` to `test_k8b_kept.py`),
this file holds a content digest per fixture set and arm, over the seeds 404, 55 and 2121 on the
eval split, strict, of every field but `task_id` and `generator_hash`, which move with any edit to a
hashed module.  It passes on the build by design; a change that moves any own task fails here.

**The own-tools generator's hash** is the second record, beside the built-in generator's frozen
`b0aa26c77259dd16a07f814fc4b250ce0ba69d372aff520663db089daa9b0db4`
(`tests/test_frozen_generator.py`): the hash of `own-2` over `generator.HASHED_MODULES` as this
file was committed.  Re-pinned 2026-10-29 for 0.3.0 (the faults design's ruled change to the
generator, Q1): the write echo moved every own task's reference observations, so every digest
below moved with the hash; the request, tools, target, stated values and reference calls of each
task are as they were, which the build measured before re-pinning.  The three new knobs' own-tools
digests are kept in `tests/test_f2_kept.py`.  Unlike the built-in one it is not frozen: a change to the own-tools tasks that edits a
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

OWN_GENERATOR_HASH = "0cf69e660b66ff0c9a36d906cd7dad10e0c7a5f63b71c950bed7bdfd67888a14"
SEEDS = (404, 55, 2121)
MOVES = {"task_id", "generator_hash"}
# 136 rows: every arm of the eight knobs each fixture set reaches (the acme sets with their
# flows); the three knobs of 0.3.0 are kept in tests/test_f2_kept.py.
MAIN = {
    ("acme-mcp", "similarity:s0"): "9a382f8185b527fdb02cd502e54e3e2d1c5a3ac9db4250e725002f5021574640",
    ("acme-mcp", "similarity:s1"): "36f6b6c9925d5d1d84b3c603a413f1a1ed309ed2b0657d0d9b2df607f2a35df4",
    ("acme-mcp", "similarity:s2"): "33204ca8316cf749db8004fb506258202a368231534cd142fbb228ec04e916db",
    ("acme-mcp", "similarity:s3"): "2702e6f96691e1c83ed1e4ee0bd8515023cc5adf4e06e8de9a858db8d7fb62ef",
    ("acme-mcp", "faults:f0"): "16df24df7c8077de51e094c38599f4ccf2dfe07fc5f115912d2c173eb0a1b5cd",
    ("acme-mcp", "faults:f1"): "907c4c6a8be94cd4ece413ef87e733388e835994f1c68d866573d758faf7ce36",
    ("acme-mcp", "faults:f2"): "1d9773dacbfb01f5156ec81d45d6316a5d2bcd54e10177e9b03482e3d9bace48",
    ("acme-mcp", "faults:f4"): "3ff7286855b5784e785e98e162caf255bfc50c78bea99e73ffc3e7d49df4eef4",
    ("acme-mcp", "history:t0"): "25c8ee3b20f19bf44ec9a1d861f4ef2763e7be7fda5e14a2dbda55d38f7fdba1",
    ("acme-mcp", "history:t300"): "ec0684c3e6f3e832e6b10ca7a085ac066558af98c0d75f7822a2584839eac892",
    ("acme-mcp", "history:t600"): "0199bec167086da550e047fedbe8ba1ad8c36041feac8c5c5e4b0a347ae0085c",
    ("acme-mcp", "history:t1200"): "63e3af290e3a675bbdfdb85eb135a386b136f094f41a348b2ab1cee1914fb2dc",
    ("acme-mcp", "history:t2400"): "c43da1a971d7b83bac56e9a69e3c9320fdf5e16eccbee951a9e48d5cd143be11",
    ("acme-mcp", "arguments:a2"): "89e9c757cd7b7c608671ded96465d468f928143ce5371d08ba7649e790215ed4",
    ("acme-mcp", "arguments:a3"): "59175325d680fdcf5867d5c9a01a7879aa06f60c8ae51aac7087194f3a7c2955",
    ("acme-mcp", "spread:p1"): "dcf107529090d84b86d2d3abe534da339cc180bcf30e540cb052bc4202697e0e",
    ("acme-mcp", "spread:p2"): "5f8d297e8775d42a24a2b3b766ded5af8da61b76b06cb93326ff605531a9d82a",
    ("acme-mcp", "spread:p4"): "fb1443270a18293c0bffd1f5a34a62e0a566e93306d50d5cd60bae051fde2f28",
    ("acme-mcp", "depth:d1"): "c2429155d23330a3ddbe24dc1596eaee4d83fe7e02c6c77054e3a543984a9047",
    ("acme-mcp", "depth:d2"): "4d16d45a17809f39cbd2a9a680086cf6cc8b3f177ff520f8a4cba64bab5a83c9",
    ("acme-mcp", "depth:d3"): "6ca725847b0577a49317c246ea2b2343dfa8a2e1f133a0a0ff3aee2be302b54f",
    ("acme-mcp", "shape:w1"): "e49c70a972c083bff9c083993fa7d11c3b20206985dd01b33ad98e90b65f8334",
    ("acme-mcp", "shape:w2"): "bcb8ae9dd4979e29f5e572c9d620bd20350d1c82844e7b16773077b74f870633",
    ("acme-mcp", "shape:w4"): "66b029bc18a9a1f61988477143e1e7cb6d0e222e89ca0784439ee0c9db3a4895",
    ("acme-openai", "similarity:s0"): "f30fec5e2e124344af70a948717bf6204d151cbc23bd08f33b9ce2cdcac6eb82",
    ("acme-openai", "similarity:s1"): "0a35ac1f478465bfba1e322c1ea54af3ec4c0bc24e4dcf7d720bc17eefe803cc",
    ("acme-openai", "similarity:s2"): "f3c20f466c4a0f2ecf236ed3cb204123225db92213461e631fb76659c3361ae7",
    ("acme-openai", "similarity:s3"): "feb0eef2cfe970e02eee5331e1e7bc3b4c1c35c211d05378d96694b222c38529",
    ("acme-openai", "faults:f0"): "1956402bab16db7678f8abb6f40accc2d2cbaa63f445017f5ade4cb3392fd2a7",
    ("acme-openai", "faults:f1"): "3271cbe74ad3cc8cc3c36742ac66ff3c3e4e1b87b01c28c6a7d21e5eb201739c",
    ("acme-openai", "faults:f2"): "ba4fd8b876502da220f9f06255b78ff720985e3e8a992d3e9fbe5e95dca7418f",
    ("acme-openai", "faults:f4"): "d98c63d121b64bbc2491e94d7b779df1d7671ce2029d1dbf904f3f98cd284f76",
    ("acme-openai", "history:t0"): "3f0478028c1df0d1761aea9bc38a4f93714ea843576478ebb669aedef4c642f4",
    ("acme-openai", "history:t300"): "8f36b49da9c36103a0b3ad258410186906614dc16d857906025d990850829b1d",
    ("acme-openai", "history:t600"): "fed7f1ada8dfc2b19b6da91a79a52866900c0f63833c2c2d4dfb53c4ec9fe457",
    ("acme-openai", "history:t1200"): "7402f2a2b04a493d4196b5c744439ea1fdbdf5f2b8599cbddad51bca6e47524e",
    ("acme-openai", "history:t2400"): "f4f4a722dd4216d334ec2b0665217e74bbb959d1d65ac3b37b6feff1a1047b94",
    ("acme-openai", "arguments:a2"): "8c4cd841a0dd74c35e516808c3e7dda1396ac8d40cdcde44359449aefc480287",
    ("acme-openai", "arguments:a3"): "26c0071496e44cf6353a9bf9a7ff3f0eb0698d0aa1863d9137dc32c13c06a64e",
    ("acme-openai", "spread:p1"): "686678f4a9b36e1bdbb570e1395bf7f18d8da063dcd3000af7484dc5ce011219",
    ("acme-openai", "spread:p2"): "3bc566b6b354a6fb218efd3f6372b06fbe72b20b6aa451318c27cb4dfb5fe41c",
    ("acme-openai", "spread:p4"): "deef62de542413eaea57fc7b1e855e49f9f93ff35a95aca65f331f997492d0b1",
    ("acme-openai", "depth:d1"): "1551e4de481f478e382ceee511674fc53f47a7134dc9f32efa6279807ef837d6",
    ("acme-openai", "depth:d2"): "eaf0fb285751fd91f1ceddd7e021a15ea2715f3193eeff54180d1b90a3f0ab95",
    ("acme-openai", "shape:w1"): "845661d9c4ad0294fcc5e17be990924fadfa8ba8dd6e820d0f9408699a3b3e3a",
    ("acme-openai", "shape:w2"): "bf14082ef8e2dd5d5f9c182bd02a09057c69a43d82cace550d0f409584b633db",
    ("acme-openai", "shape:w4"): "c62158cecb802881bad0c635f610dba03c8a8630ccc2f7872e82447e8978e2ab",
    ("acme-openapi-3.0", "similarity:s0"): "13f5891ea5b9a160bb579e94e13885ed9776891016d85a2cb0c4e1d3fd567e8a",
    ("acme-openapi-3.0", "similarity:s1"): "ad13fa00ca9484978cc259fd46991cc185117d1f516d604c90212520a03ae190",
    ("acme-openapi-3.0", "similarity:s2"): "2f80a47ce5bb961a42b5643516b50cd3d621145e89e9b79f80e5b791f4ea9f22",
    ("acme-openapi-3.0", "similarity:s3"): "09f0e99b789a7b7c496d86480ac63bf27a22c743ee83d3cc6eb01b5b2da56bfa",
    ("acme-openapi-3.0", "faults:f0"): "00fd9787f5857db06dcc85b2bc6514966053e9fd24ebb1aed723607b40e97eaa",
    ("acme-openapi-3.0", "faults:f1"): "06ae2b577c997415e18f1c3c480a9eb447549e0574595b3eac872f510e79bb6e",
    ("acme-openapi-3.0", "faults:f2"): "67d2e13a9b6d220e6f115d675480867bf20c2e490a902f3760d2aacb91ac0106",
    ("acme-openapi-3.0", "faults:f4"): "1e22b08bee1742dcefe694943832e0629d753349043517b840da49c177db4c72",
    ("acme-openapi-3.0", "history:t0"): "d1a9e28c14725dcda6adaa4cf85ea5901e1db6a73425419eea46b9070933f25a",
    ("acme-openapi-3.0", "history:t300"): "3a562a8faa2c291be76b1703b6585210cd7b29ff40dfe00a2b81c09acb73f053",
    ("acme-openapi-3.0", "history:t600"): "37804d0d676ebad22044531ef101a56e749844e7463ffbd8fb85abe55846729b",
    ("acme-openapi-3.0", "history:t1200"): "f92da2710338bf03928433bea8013487350f35d0ee89d3928dfcabca2e19a869",
    ("acme-openapi-3.0", "history:t2400"): "a3776c0024809c9cc4465c3c027d600dddf151ceaaa148194b8625d393909f61",
    ("acme-openapi-3.0", "arguments:a2"): "7c0f8d9af10e8b16314f37bb9edf16ad972e177b26225d68cdfa28780bfbd42e",
    ("acme-openapi-3.0", "arguments:a3"): "591a49bf8ff0ac56b283343bfd48b3ff67a26ef99054c9969e510fbe28291c4c",
    ("acme-openapi-3.0", "spread:p1"): "43e4536b3650468e9154e345c1a6bdcf6d8cbe270d1b73484625e2ee08f0f8a6",
    ("acme-openapi-3.0", "spread:p2"): "2427fc7682c13691d46c1c1ca7f7d681e8bc506803969f91f5e85c6cdfbb252b",
    ("acme-openapi-3.0", "spread:p4"): "d71582709d04f814ede008910bac4805e79948e92bb57117f1d1a3c4c3772400",
    ("acme-openapi-3.0", "depth:d1"): "f5965d75392ff6d838fd0340b9027a012e218a01b19ec8ce05ab9edc39251649",
    ("acme-openapi-3.0", "depth:d2"): "3b40342cfb1bf9684007328c70c3067cf4ad418d640e255558fb0ed426d185e6",
    ("acme-openapi-3.0", "depth:d3"): "d66f23d6fea34e823ad277aadf27a3d2d2766aca0ae35dc9e5046f66a22a222e",
    ("acme-openapi-3.0", "shape:w1"): "66ea531e1c77c2aaf6437b26621698c275d7162710183fadfc847ce18d1ddf1a",
    ("acme-openapi-3.0", "shape:w2"): "6238743147a82a181391250277c5d535afed5ca02390649aaec64f941b88c41a",
    ("acme-openapi-3.0", "shape:w4"): "1aee01636e14dffc3f3168337c2c086a8a468ac527676fb135887dbce44daef3",
    ("acme-openapi-3.1", "similarity:s0"): "70ccfa7133f6f6d72f62793e7b68eb3535653d30b4a54edeec30a7b9a086110d",
    ("acme-openapi-3.1", "similarity:s1"): "781d093aefb7ba7c19f8b0e67d7eaef0a8a9111aadaffe8cbe250276a1cb043a",
    ("acme-openapi-3.1", "similarity:s2"): "182aa21c4193ad461d48af9cfb3991cfcab407588bcacfea02701d1eb5097f87",
    ("acme-openapi-3.1", "similarity:s3"): "f010d11eaf32157d38344fbacb33a52236a46766659708573d6fdb8a0715c4ee",
    ("acme-openapi-3.1", "faults:f0"): "1f3ddac673ac2cb31170328279bb2b0ad3ee288b8a6c545a480a2b12e3028bb7",
    ("acme-openapi-3.1", "faults:f1"): "e0582ad4a7c59fbd392457ff7530d6a7292a237dc15d5c266ab52c5ab6a8966a",
    ("acme-openapi-3.1", "faults:f2"): "da7f7bc78222fae788138586a8edf125da3bd4cfd2241d4e85dbbef0fbde38a5",
    ("acme-openapi-3.1", "faults:f4"): "ef479d8d6b99ab829f5b641805ec76678d9cf281985f31965b9d9c1dd62d3956",
    ("acme-openapi-3.1", "history:t0"): "835a978ca7faf5c20cc2f00cb16bee94e0b40a6539717b6760e16e8115c33cbd",
    ("acme-openapi-3.1", "history:t300"): "949554f723371eca836f638c9fb446071e4e98a62c7c79841f7f92ee21cf5c24",
    ("acme-openapi-3.1", "history:t600"): "10b270dba0c71eb60d303f61928e9f4ebe8f8c392600713864c009f9567db15b",
    ("acme-openapi-3.1", "history:t1200"): "ca3ad8d8c9610c4c881ee14f00f364069af3d5984c6dc060bf684b92090ec2d3",
    ("acme-openapi-3.1", "history:t2400"): "30e3faf5b37cd984bbc43e5a7f19fb83ec68809b60775cba7a7462bd8899437d",
    ("acme-openapi-3.1", "arguments:a2"): "44de0660cacc9ecc4b4a9c3b441889d40698475ce96b4351feed1b1679ec6f64",
    ("acme-openapi-3.1", "arguments:a3"): "898161cd20c96ffa43d9e859b6e9fb766520286df00e32542a301465728130ac",
    ("acme-openapi-3.1", "spread:p1"): "f7f4470a80c69ebe9150cd049a210915fb8e918a0306d920b6940e620552a57a",
    ("acme-openapi-3.1", "spread:p2"): "7935d740b7a43122ef5f4cf6e561b6ecb9734c1b245b392054d922bb25399846",
    ("acme-openapi-3.1", "spread:p4"): "1807b69b26e6e1f43e708790860397bce26068e7d02cd039ddaf3f57a40b4bb2",
    ("acme-openapi-3.1", "depth:d1"): "7531cc9a8a39378bba817e9d411051f4c706fd8fb411d22d560fdd9f88bab11a",
    ("acme-openapi-3.1", "depth:d2"): "ed582ed53c93289a4450b75ff79fc2a773813c82c40a0af0f581bcefda7c7eee",
    ("acme-openapi-3.1", "depth:d3"): "bf103e0be3a25a2e106bd7f8f2db4a4f9de176dd62af386fae413a917cf68ae4",
    ("acme-openapi-3.1", "shape:w1"): "aa28bd4736a87552fda3654d709b2989c5db66baffbbc8dd2b71e534e8eba850",
    ("acme-openapi-3.1", "shape:w2"): "ff3dcf341547b443c29ab26eca5ee91f5f2a6063fb0e7d38f4e143001f976d0a",
    ("acme-openapi-3.1", "shape:w4"): "b87b5744677b0bb031c40983e922a3776a4e5f0c7a055ce36cf7e31cb272ccbc",
    ("petstore", "similarity:s0"): "384638397ad824917ae27a5ebe1b027a976f1c7078dd80c4061ef9c1966b807c",
    ("petstore", "similarity:s1"): "dc32da7a28487372b26686875ca42b1a020add9b82b803cdc32da1c3aa445fe5",
    ("petstore", "similarity:s2"): "74a66ee3316b1734df9ecc8974bce439744a9a31d4c71af22bd408ff7322c70d",
    ("petstore", "similarity:s3"): "41d314155535585889621e5f6cf2198b115fe1aa09163f26b3af8f2c714ab076",
    ("petstore", "faults:f0"): "bc3b15baad3c9192da44908bbf7186e4ef6f8d80b627d685e122b05e99654fe9",
    ("petstore", "faults:f1"): "9d00b9d8bc833cb95b6503a448ab4fb842055134c1e2489bb57e309414a11968",
    ("petstore", "faults:f2"): "7b1a002c7e646de04de1525a3716a0691465dacc73d8d6a2977bf9f30a11bdd9",
    ("petstore", "faults:f4"): "8fa2bc4f4bcee26b3e5ede35818f46a9eef3d2c797139555455cf302cacdf1c8",
    ("petstore", "history:t0"): "23ea774574259550c8f3039ca234f82d4434e022b967c907f5543280d8cc6406",
    ("petstore", "history:t300"): "842190ac0c4a92c2ad9505ce08c36cdf509639bd3db792fbedbd4f4c94be7fa1",
    ("petstore", "history:t600"): "6a914036b875591c1be6c4489d067c65ff5a049b73333a22d47e21aacdf14e41",
    ("petstore", "history:t1200"): "9e6b0ad9d30ba6b89842f6a29bfd43d31632fff483f2478b55f4d00d7a441f88",
    ("petstore", "history:t2400"): "1915ae8e5c094b931aa03f420a106bbb1bca88a3c17db28d07b9ac4f576bafc0",
    ("petstore", "block:k8"): "6fc5ec1507c6b29d9ef5e78c7187c629071f3178f6decfc6da2424197fa85065",
    ("petstore", "block:k16"): "9ce321b49c7724d985aee7fa6e943d2928f26b1d3593dcb825c7af9343256316",
    ("petstore", "arguments:a2"): "2cad9dd52ceeb6d150941460a147bb8c6eaea20b36f7b3fbda27c18ba379ccd6",
    ("petstore", "arguments:a3"): "63586ab5a158cc109847614e18cb6a424e7d60c7df02255e47497d03d8d74c45",
    ("petstore", "arguments:a4"): "c7bac98f8545635fb966be98a74c5f903c7121250d1a6014253ea0b0261c95cd",
    ("petstore", "arguments:a5"): "aa04cf50a165bafbe78f4b3e45eeada707a7e5e7df2aa7eaaf1a3525aa47d695",
    ("petstore", "arguments:a6"): "d50c0b354ae4abeafede4d56420b5a23694a49755226c2c8b3a88ee137cbe221",
    ("petstore", "spread:p1"): "28bc962e31ffb024066b170b37acee0aed5dd184680897ae9d2431390dd1a59c",
    ("petstore", "spread:p2"): "5fe6e4945c4d630139e0c0188e1a99c019fbe0c321bc62736b3f30e348cc48fa",
    ("petstore", "spread:p4"): "4b3f9d849e35997f506a78b0657ac41a79c61f2b9c32583b852e216e99ac3738",
    ("everything", "similarity:s0"): "6cdc8ca9e0d2433cd64a6f3eb8fe68cbcdc9310ccd5fcc43c6024910d83d248c",
    ("everything", "similarity:s1"): "46ebc7646c16eccc9342f4825a127a5543cf12ed6b1b528c201ea34d471a9477",
    ("everything", "similarity:s2"): "7c79618496f11b02be9f93e428bd02961e01c814aa0e01ec219d9369f2eeb37c",
    ("everything", "similarity:s3"): "48805b64b1dff1a17f36dd7f7eaa46307db6ab8dd040d8f568ad4c8245992bcb",
    ("everything", "faults:f0"): "cec05eb0da327b7d3bb154a7d7eed1abf6361e91fd1c98b1139d99898c61f6b0",
    ("everything", "faults:f1"): "8d7d1064e85797aa94fb5fce0c6fce23280e4e4e3440c443a6f9806d97554b97",
    ("everything", "faults:f2"): "4a315bba88724a8a292d957db0b2cbfb83fdb6ad0e4ba107a9460b9898fe993e",
    ("everything", "faults:f4"): "ee73547f83b3ebb9122a7b9fb4daca50c9168b6c98168836918bdd5895e8242a",
    ("everything", "history:t0"): "613cfcf16e78799e9233a3fa893c594a8f4db21e2b690b9f21e22f410b421f12",
    ("everything", "history:t300"): "a24631a92878c2f6edb463d2472ff464fd3d1cb3bdab786a88d8cfff9c494445",
    ("everything", "history:t600"): "9e9790317d80d54eb0530ce6ef069668af8f6f8e9771f60c88b1ba6e8d676cd1",
    ("everything", "history:t1200"): "95b30557a628420df7325716c550bb7aa867217b8dee0b7544e0ab4daac7974f",
    ("everything", "history:t2400"): "95abe4ac46f0326bdfeba6e0228d6d3a090dc0304b9b1b30f61450fb52f0cb97",
    ("everything", "block:k8"): "0e783d348a4b43618819ccb9e04fafa122d70038bccad57e6359403542f8544e",
    ("everything", "arguments:a2"): "d52c7115f7b2ea23aeded730aa3e3cb6627bbd773a45807a6f6ae68dbf98cd61",
    ("everything", "spread:p1"): "b2d1fe58cfb17a38566d19370d72ca174653d1d63a0a34584d0f1997798a4e87",
    ("everything", "spread:p2"): "6f374203cbbcac52021111fb3a1dd33e5784a52c115ffda60bd8ae95b6b416cb",
    ("everything", "spread:p4"): "eafde224a4619fa2319217a6f95aa2b415a34542fcdc802ab855b04cdea776b2",
}


def plain(value: object) -> object:
    return list(value)  # type: ignore[call-overload]


def test_the_own_tools_generator_hash_is_the_recorded_one() -> None:
    assert generator().generator_hash() == OWN_GENERATOR_HASH, (
        "the own-tools generator's hash moved: a hashed module changed; record the new hash here"
        " and in the change's record, with the digests of the tasks that moved"
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
