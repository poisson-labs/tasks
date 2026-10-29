"""The 0.3.0 transport-fault knobs' tasks keep their content, frozen as a test.

As the knobs' design states it for every knob built since the freeze: the 840 published tasks keep
their content (frozen `tests/test_k1_content.py`), and so do the tasks of the seven newer knobs
(`tests/test_k4_kept.py` to `tests/test_k8b_kept.py`).  Nothing held the three knobs of 0.3.0: the
frozen `tests/test_f2_*.py` tests pin their structure (the line, the plan, the sentence, the
retries, the own-tools echo and reflection) and not their content, and a later change to a draw,
a sentence's bytes or the own generator's target draw would pass every one of them.  So the
build pins their content with digests, the way every knob's build did, in a file of its own,
read by `tests/test_frozen_generator.py` for the built-in half.

**The built-in half**, `MAIN`: the timeouts and ratelimits arms (every candidate level and the
control) at every card seed on both splits, keyed `(arm_id, split)` as `tests/test_k4_kept.py`'s
faults digests are, of every field but `task_id`, `generator_hash` and `pins`, which move with
any edit to the generator's modules.  `landed` has no built-in tasks (ruled, Q2 option a of the
faults design), so it has no digest here.

**The own-tools half**, `OWN`: every arm of the three knobs each fixture set reaches (the acme
sets with their flows), at the seeds 404, 55 and 2121 on the eval split, strict, keyed
`(set, arm_id)` as `tests/test_o2b_kept.py`'s digests are, of every field but `task_id` and
`generator_hash`.

Computed on the build, branch `f2-build`, the built-in generator at
`` and the own-tools generator at
``.  It passes on that tree by design; a change that
moves any of these tasks fails here.  What a deliberate change updates: the digests of the arms
whose tasks moved, and the two hashes in their records.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Any

import pytest

from poisson_tasks.knobs import arm_id
from tests.k3_support import CARD_SEEDS, made
from tests.o2_support import every_arm, fixture_sets, flows_for, generator

MOVES = {"task_id", "generator_hash", "pins"}
OWN_MOVES = {"task_id", "generator_hash"}
OWN_SEEDS = (404, 55, 2121)
NEW = ("timeouts", "ratelimits", "landed")

# 20 rows: timeouts and ratelimits, the four levels and the control, on both splits.
MAIN = {
    ("timeouts:o0", "eval"): "659239c916998b2779852b23c32709efb68d1674817044965b3ceb314a3773d3",
    ("timeouts:o1", "eval"): "b765c3245558b3efed5441e75281efe912dbe41531961c8a5ba280992674f863",
    ("timeouts:o2", "eval"): "8aca6e610d119bf729605e1a77fbcdf26c97cd6eec5ef2a2016c7815152f7720",
    ("timeouts:o4", "eval"): "167ce4fca1bfd592f5ce44873ab78f04a9610004b7fe9277e31e0279d95eb6e0",
    ("timeouts:o0+len(o4)", "eval"): "22a2d5164cff2b7c3e295565d7a0267d8ee69c1be963d54f52c23e5d51ea8d89",
    ("timeouts:o0", "train"): "adf2995ccc61cfbbdd463964e1005c7a0ed397126800bc94b8e799ca081f063e",
    ("timeouts:o1", "train"): "93d8a980cf2dca97eb1ac43b22d71dbf9a9495a5d931374bdbd637dce172409d",
    ("timeouts:o2", "train"): "75348073cb7f2ac80d948fb31da89175fc931bfbea4aff39c43a00b05c7bc240",
    ("timeouts:o4", "train"): "ed7bc427261a89c38a021ae7b1f55519ac8f1897080ae1b0912a602c86d664a1",
    ("timeouts:o0+len(o4)", "train"): "9ab0a0acb827ca446a9ac4253112598be8fb043a7bb218d822e9b68b445309c8",
    ("ratelimits:r0", "eval"): "5b3bc86e137904f991f1107dc8b7d18bf54cd54ea64d197031b69d1f5d27a725",
    ("ratelimits:r1", "eval"): "efd33c43f96635343c38e17544635596d9d1779226dea98a4e35b1de861371fc",
    ("ratelimits:r2", "eval"): "6db0600e95ea022bcc389b0232f9922523c21dd5d12a7e58be028a9f1ac7269e",
    ("ratelimits:r4", "eval"): "29d76853fd8678ce5004a5498e962492498155489659156092e8a5550c250417",
    ("ratelimits:r0+len(r4)", "eval"): "ba791d5f373302c26d5a5cc7ee58365ec21c791c1a12650aca6bacedb8709983",
    ("ratelimits:r0", "train"): "504e6fac06b053ffa19881c65cb688b29ccf0a8d174a01672d31b2aa67e4193e",
    ("ratelimits:r1", "train"): "fc65dd5e57163d569312e51e3ef2ac7decdc931df7babb09ca78d1dd9ba52450",
    ("ratelimits:r2", "train"): "54868c4292f17add3eb5ad5638acac35ca36d5886ce03757c6fcd7355bf7f33f",
    ("ratelimits:r4", "train"): "472a476db47e2014fa630fa99cfdae824343d9c821eed0db575d5b727a4c053b",
    ("ratelimits:r0+len(r4)", "train"): "be3c0cc9cb9e0e9592291f4d3336a49d651cadf22e337c9231629e6385dc7d54",
}

# 58 rows: every arm of the three knobs each fixture set reaches.
OWN = {
    ("acme-mcp", "timeouts:o0"): "4804bdab0470bc77906317881a9e1125e076b97bad3a9687c7fcf134db109620",
    ("acme-mcp", "timeouts:o1"): "af53ee68ba506448b6afbbca931d741f3ab484c67f1f6325d344dd3073de3633",
    ("acme-mcp", "timeouts:o2"): "d73f800169e9e4dfef40a81e0c06269bc8170c9051d5197ddf3531bd0309f1dc",
    ("acme-mcp", "timeouts:o4"): "f1cca3beb4c73e16b35a396d58205c9e35345b56d562c63ce0083a0700c27b41",
    ("acme-mcp", "ratelimits:r0"): "f871b95c7aed822451abeb3383259683ca0670008e23031007a5ee5b2c48cd53",
    ("acme-mcp", "ratelimits:r1"): "c53cbd783d0cd435e8947f56f523eca9e92d439703c7d6ae07d10c862e440fa1",
    ("acme-mcp", "ratelimits:r2"): "a6bbadcbbfb9e16e3a4e2f68b528a1cb119446b3a69695c28ffe388339a38907",
    ("acme-mcp", "ratelimits:r4"): "9b86d253590578438e19bf0f566b9114eae274024fb6285c0ecc82b47732ef87",
    ("acme-mcp", "landed:l0"): "2388a27f3cc7cbb2b35ea0b80b09bf948c5c1e2caab96563b4614e02b0fa7882",
    ("acme-mcp", "landed:l1"): "0d9c2c645b923abe1aba7f2fa24718eb37b694e75e8ab49f65c296253a5fb0c7",
    ("acme-openai", "timeouts:o0"): "c418acb17387b07ff2d9fa6f06afc7fbd16d8b034daf2af5c6d0f6cbb05d3963",
    ("acme-openai", "timeouts:o1"): "d5aa7e132d415a8b21d44708103e1a204f2a5e38aec874986955fef990959040",
    ("acme-openai", "timeouts:o2"): "0d52da7304444b8c7b8cd86d81587b50453af70424008f0c07da462754c06d38",
    ("acme-openai", "timeouts:o4"): "688df3418c187ba94ab87e0d1092c0b21e3d7440d4be42f6a9bdb51dc198a07f",
    ("acme-openai", "ratelimits:r0"): "9967394bc01122aeb34603f8aa230d60781a33c5929915da7a617cc3238b9a04",
    ("acme-openai", "ratelimits:r1"): "ff5c8c795914b099919630f6e9857f1e638919f6d79ca63f688a3f0c5e533390",
    ("acme-openai", "ratelimits:r2"): "1f1d230833b55d69ec115e225854b4306c23bc50308c06eb636edecd3a7faaea",
    ("acme-openai", "ratelimits:r4"): "37297808fed5dc01400bb231854fd41d8f105fadc2fff01e00f4545a74a4d0f6",
    ("acme-openai", "landed:l0"): "2ac35d6c27af7616f917fa06fbad75eb9c047da67a73d289b6a5ae251df54fc4",
    ("acme-openai", "landed:l1"): "c9e0ee72fec88595845ee2a5012f056275992a41287da978b680ca2bdaee610d",
    ("acme-openapi-3.0", "timeouts:o0"): "f84c0e73ca6d0534797b6fd38dd63e0520db581cd74b103baededd7cb01d0df9",
    ("acme-openapi-3.0", "timeouts:o1"): "30316ce10dd75d57a36defce723f11baf8e4cc85fdca8fe5601fe63b9a039c67",
    ("acme-openapi-3.0", "timeouts:o2"): "7b58406c77d0c81cf01ee09dd26e833e4327c1783f78eef08539e51488656faa",
    ("acme-openapi-3.0", "timeouts:o4"): "25ce90c76a3252b91abe229d4dba412bb80b53b79ab96b2fac39e89058c9241b",
    ("acme-openapi-3.0", "ratelimits:r0"): "c51ccffc8de83f7d53adb44695e35b062e44e5c2e87ba517fcee815e599f98a1",
    ("acme-openapi-3.0", "ratelimits:r1"): "2246241054c7847f138bc6a7da2c67d82ea38924ead1713b71d78d508b12f1f5",
    ("acme-openapi-3.0", "ratelimits:r2"): "37c41b423b959a6e90b700d7063faad130a4d31230ced58043563b6128c93de8",
    ("acme-openapi-3.0", "ratelimits:r4"): "5966604323dc32a05dc5d7c3b2f35a63424b4c2e053d85220f87c42e1a6e7aa6",
    ("acme-openapi-3.0", "landed:l0"): "a6ecc6d2aa3568be8e0b5d5a2d0bfbb5bb393b19364c2858e452990302a02986",
    ("acme-openapi-3.0", "landed:l1"): "a71d4f82e7daf449ccabc47b0d0d9ae9db15c396fe6dc5d0fc4a5a0f23d8c6f2",
    ("acme-openapi-3.1", "timeouts:o0"): "a0dadf773c0971d06066ec87fdb69cbe71e5f16f55ffa8c12de96807fd63519c",
    ("acme-openapi-3.1", "timeouts:o1"): "a36cc5d9b9cd135eace53fdc95b77ffc582b072b381d967dfaf1f112659c9bfb",
    ("acme-openapi-3.1", "timeouts:o2"): "822e5e1674d8b7042bf7b3d7bb28066a0faf0fa1a38dda5ad8f02fac04c5e0fe",
    ("acme-openapi-3.1", "timeouts:o4"): "62e56f20d3fcac647d067bd8cc9e9c2924431effc8e62e01fbb9c3dc6bafd9d9",
    ("acme-openapi-3.1", "ratelimits:r0"): "a72dec3c5806001d519db22d3b386eed7f27d0baf62144ef89943dbb13cd5037",
    ("acme-openapi-3.1", "ratelimits:r1"): "5b8707981ea476adada4b0a203fe020d57d106330515a62f57190c448e79230e",
    ("acme-openapi-3.1", "ratelimits:r2"): "ddbe93e92c68377257c595d5c4fc27726ba1547b2ee70caf4fdceb2ae15d2fe6",
    ("acme-openapi-3.1", "ratelimits:r4"): "22f1dd3172008c27954781d75e40ddbcb682db80070ae26f2e12ee6385bec6a4",
    ("acme-openapi-3.1", "landed:l0"): "2b52a96bcdc2aa79a1dff36511da4d986c99a3ff3bed41f5f2c98a09ba10f38c",
    ("acme-openapi-3.1", "landed:l1"): "749cdd4f7efbb8a3abf20002da0d83bd4f3fdac0c2f37207847180eefe0f7f25",
    ("petstore", "timeouts:o0"): "1abd35ab19f20fd896edcb6e4ff1de7ee839c7437b40cf6b6d32af871bc74ba8",
    ("petstore", "timeouts:o1"): "ed25081218927f7dad2f1ac9a7200b49bbcfe7e4bf03d3ba615e751a540e3c32",
    ("petstore", "timeouts:o2"): "c304b897f85a9fe7cc28347eddfe8e6e29d00f1ff441d39d985af99b8d94e0fe",
    ("petstore", "timeouts:o4"): "77df50f4a7ee37a6a0aebe8fbd4bc7401f06813fd6888fc7613193e285814c9c",
    ("petstore", "ratelimits:r0"): "f4984c983e31072f940ed3c4b0ce00f9e0e138dc29f345a2be472aa7213ff897",
    ("petstore", "ratelimits:r1"): "f208b71d67d2e6fce179a9cf6228e7c3676d2dbb0ccc87ded712127145b6b59c",
    ("petstore", "ratelimits:r2"): "4d3e11789dfd63594632ebfe548668a61274ee6fe4a8b240c134865e07481f5a",
    ("petstore", "ratelimits:r4"): "57479d5950289fa0c045fbf8b612d35579cdf0de27f48a41df92d2abe1624ce7",
    ("petstore", "landed:l0"): "a91c27147ddff709c876a1a92d916483dc113b2825a0f1eec3ce831b2c65ed92",
    ("petstore", "landed:l1"): "a92c238606c46a8bc1853e3e76bc24a0d21c20589093485cea3adbec99abb5c8",
    ("everything", "timeouts:o0"): "305cb022a72e6a570e5c721844ff8b43b6d20ab02d043d329f19f7d4c94cbc44",
    ("everything", "timeouts:o1"): "fc19bf8e846a30114fe04cf4e12b3a1116a20bcd876ed3ec0f47b0b698d2d275",
    ("everything", "timeouts:o2"): "b18ff6e6030f3ec1c8fcf73c2b637d90cddeaf8abbbf6d68f85fc16e01421c0d",
    ("everything", "timeouts:o4"): "fa3dd9592fa44a4012b515812b6f308eda931295c30f6c30bfd79b94013ae2f0",
    ("everything", "ratelimits:r0"): "98ef3a2727ccd2fc9fe87f828863204bf0c2a8e83ff1ea8e95bdce94b719cbda",
    ("everything", "ratelimits:r1"): "162b19c9eccabe003d539be25329b4206498e0c354bdb0120a42c8c67c00185e",
    ("everything", "ratelimits:r2"): "b577814b0d6494fa3028400bbacb2261d077a5aa5fe6bdf57e706ffc712cd701",
    ("everything", "ratelimits:r4"): "edf9d68a6b0fe840aa710d520f569a82ade0f5eea9198911b08b4e58e5e02e38",
}


def plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    return list(value)


@pytest.mark.parametrize(("arm", "split"), sorted(MAIN))
def test_the_timeouts_and_ratelimits_tasks_keep_their_content(arm: str, split: str) -> None:
    digest = hashlib.sha256()
    for seed in CARD_SEEDS:
        bundle = made(arm, seed, split)
        content = {
            field.name: getattr(bundle, field.name)
            for field in dataclasses.fields(bundle)
            if field.name not in MOVES
        }
        digest.update(
            json.dumps(content, sort_keys=True, separators=(",", ":"), default=plain).encode()
        )
        digest.update(b"\n")
    assert digest.hexdigest() == MAIN[(arm, split)], (
        f"the {arm} tasks on the {split} split moved: a deliberate change updates this digest"
    )


def test_the_own_half_holds_every_arm_of_the_three_knobs_each_set_reaches() -> None:
    expected = {
        (label, arm_id(spec))
        for label, toolset in fixture_sets().items()
        for spec in every_arm(toolset, flows_for(label))
        if spec.knob in NEW
    }
    assert set(OWN) == expected


@pytest.mark.parametrize(("label", "arm"), sorted(OWN))
def test_the_own_tools_tasks_of_the_three_knobs_keep_their_content(label: str, arm: str) -> None:
    toolset, flows = fixture_sets()[label], flows_for(label)
    (spec,) = [s for s in every_arm(toolset, flows) if arm_id(s) == arm]
    digest = hashlib.sha256()
    for seed in OWN_SEEDS:
        bundle = generator().generate(toolset, spec, seed, flows=flows)
        content = {
            field.name: getattr(bundle, field.name)
            for field in dataclasses.fields(bundle)
            if field.name not in OWN_MOVES
        }
        digest.update(json.dumps(content, sort_keys=True, separators=(",", ":"), default=plain).encode())
        digest.update(b"\n")
    assert digest.hexdigest() == OWN[(label, arm)], (
        f"the own-tools tasks of {label} {arm} moved: a deliberate change updates this digest"
    )
