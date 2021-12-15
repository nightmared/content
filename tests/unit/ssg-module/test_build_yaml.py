import os
import tempfile

import yaml
import pytest
from ssg.build_cpe import ProductCPEs

import ssg.build_yaml
from ssg.yaml import open_raw


PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..", )
DATADIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "data"))


def test_serialize_rule():
    filename = PROJECT_ROOT + "/linux_os/guide/system/accounts/accounts-restrictions/password_storage/no_empty_passwords/rule.yml"
    rule_ds = ssg.build_yaml.Rule.from_yaml(filename)
    rule_as_dict = rule_ds.represent_as_dict()

    with tempfile.NamedTemporaryFile("w+", delete=True) as f:
        yaml.dump(rule_as_dict, f)
        rule_ds_reloaded = ssg.build_yaml.Rule.from_yaml(f.name)

    reloaded_dict = rule_ds_reloaded.represent_as_dict()

    # Those two should be really equal if there are no jinja macros in the rule def.
    assert rule_as_dict == reloaded_dict


TEST_TEMPLATE_DICT = {
    "backends": {
        "anaconda": True,
        "anaconda@rhel7": False,
    },
    "vars": {
        "filesystem": "tmpfs",
        "filesystem@rhel7": ""
    },
}


def test_make_items_product_specific():
    rule = ssg.build_yaml.Rule("something")

    rule.identifiers = {
        "cce@rhel7": "CCE-27445-6",
        "cce@rhel8": "CCE-80901-2",
    }

    rule.template = TEST_TEMPLATE_DICT.copy()

    rule.normalize("rhel7")
    assert "cce@rhel7" not in rule.identifiers
    assert "cce@rhel8" not in rule.identifiers
    assert rule.identifiers["cce"] == "CCE-27445-6"

    assert "filesystem@rhel7" not in rule.template["vars"]
    assert rule.template["vars"]["filesystem"] == ""
    assert "anaconda@rhel7" not in rule.template["backends"]
    assert not rule.template["backends"]["anaconda"]

    rule.identifiers = {
        "cce": "CCE-27100-7",
        "cce@rhel7": "CCE-27445-6",
    }
    with pytest.raises(Exception) as exc:
        rule.normalize("rhel7")
    assert "'cce'" in str(exc)
    assert "identifiers" in str(exc)

    rule.identifiers = {
        "cce@rhel7": "CCE-27445-6",
        "cce": "CCE-27445-6",
    }
    rule.normalize("rhel7")
    assert "cce@rhel7" not in rule.identifiers
    assert rule.identifiers["cce"] == "CCE-27445-6"

    rule.references = {
        "stigid@rhel7": "RHEL-07-040370",
        "stigid": "tralala",
    }
    with pytest.raises(ValueError) as exc:
        rule.make_refs_and_identifiers_product_specific("rhel7")
    assert "stigid" in str(exc)

    rule.references = {
        "stigid@rhel7": "RHEL-07-040370",
    }
    rule.normalize("rhel7")
    assert rule.references["stigid"] == "RHEL-07-040370"

    rule.references = {
        "stigid@rhel7": "RHEL-07-040370",
    }
    rule.template = TEST_TEMPLATE_DICT.copy()

    assert "filesystem@rhel8" not in rule.template["vars"]
    assert rule.template["vars"]["filesystem"] == "tmpfs"
    assert "anaconda@rhel8" not in rule.template["backends"]
    assert rule.template["backends"]["anaconda"]

    rule.references = {
        "stigid@rhel7": "RHEL-07-040370,RHEL-07-057364",
    }
    with pytest.raises(ValueError, match="Rules can not have multiple STIG IDs."):
        rule.make_refs_and_identifiers_product_specific("rhel7")


def test_priority_ordering():
    ORDER = ["ga", "be", "al"]
    to_order = ["alpha", "beta", "gamma"]
    ordered = ssg.build_yaml.reorder_according_to_ordering(to_order, ORDER)
    assert ordered == ["gamma", "beta", "alpha"]

    to_order = ["alpha", "beta", "gamma", "epsilon"]
    ordered = ssg.build_yaml.reorder_according_to_ordering(to_order, ORDER)
    assert ordered == ["gamma", "beta", "alpha", "epsilon"]

    to_order = ["alpha"]
    ordered = ssg.build_yaml.reorder_according_to_ordering(to_order, ORDER)
    assert ordered == ["alpha"]

    to_order = ["x"]
    ordered = ssg.build_yaml.reorder_according_to_ordering(to_order, ORDER)
    assert ordered == ["x"]

    to_order = ["alpha", "beta", "alnum", "gaha"]
    ordered = ssg.build_yaml.reorder_according_to_ordering(
        to_order, ORDER + ["gaha"], regex=".*ha")
    assert ordered[:2] == ["gaha", "alpha"]


@pytest.fixture
def env_yaml():
    env_yaml = dict()
    product_yaml_path = os.path.join(DATADIR, "product.yml")
    product_yaml = open_raw(product_yaml_path)
    product_yaml["product_dir"] = os.path.dirname(product_yaml_path)
    env_yaml["product_cpes"] = ProductCPEs(product_yaml)
    return env_yaml


def test_platform_from_text_unknown_platform(env_yaml):
    with pytest.raises(ssg.build_cpe.CPEDoesNotExist):
        ssg.build_yaml.Platform.from_text("something_bogus", env_yaml)


def test_platform_from_text_simple(env_yaml):
    platform = ssg.build_yaml.Platform.from_text("machine", env_yaml)
    assert platform.to_ansible_conditional() == "ansible_virtualization_type not in [\"docker\", \"lxc\", \"openvz\", \"podman\", \"container\"]"
    assert platform.to_bash_conditional() == "[ ! -f /.dockerenv ] && [ ! -f /run/.containerenv ]"
    assert platform.to_xml_element() == b'<?xml version=\'1.0\' encoding=\'utf8\'?>\n<ns0:platform xmlns:ns0="http://cpe.mitre.org/language/2.0" id="machine"><ns0:logical-test operator="AND" negate="false"><ns0:fact-ref name="cpe:/a:machine" /></ns0:logical-test></ns0:platform>'


def test_platform_from_text_simple_product_cpe(env_yaml):
    platform = ssg.build_yaml.Platform.from_text("rhel7-workstation", env_yaml)
    assert platform.to_bash_conditional() == ""
    assert platform.to_ansible_conditional() == ""
    assert platform.to_xml_element() == b'<?xml version=\'1.0\' encoding=\'utf8\'?>\n<ns0:platform xmlns:ns0="http://cpe.mitre.org/language/2.0" id="rhel7-workstation"><ns0:logical-test operator="AND" negate="false"><ns0:fact-ref name="cpe:/o:redhat:enterprise_linux:7::workstation" /></ns0:logical-test></ns0:platform>'


def test_platform_from_text_or(env_yaml):
    platform = ssg.build_yaml.Platform.from_text("ntp or chrony", env_yaml)
    assert platform.to_bash_conditional() == "( rpm --quiet -q chrony || rpm --quiet -q ntp )"
    assert platform.to_ansible_conditional() == "( \"chrony\" in ansible_facts.packages or \"ntp\" in ansible_facts.packages )"
    assert platform.to_xml_element() == b'<?xml version=\'1.0\' encoding=\'utf8\'?>\n<ns0:platform xmlns:ns0="http://cpe.mitre.org/language/2.0" id="chrony_or_ntp"><ns0:logical-test operator="OR" negate="false"><ns0:fact-ref name="cpe:/a:chrony" /><ns0:fact-ref name="cpe:/a:ntp" /></ns0:logical-test></ns0:platform>'


def test_platform_from_text_complex_expression(env_yaml):
    platform = ssg.build_yaml.Platform.from_text("systemd and !yum and (ntp or chrony)", env_yaml)
    assert platform.to_bash_conditional() == "( rpm --quiet -q systemd && ( rpm --quiet -q chrony || rpm --quiet -q ntp ) && ! ( rpm --quiet -q yum ) )"
    assert platform.to_ansible_conditional() == "( \"systemd\" in ansible_facts.packages and ( \"chrony\" in ansible_facts.packages or \"ntp\" in ansible_facts.packages ) and not ( \"yum\" in ansible_facts.packages ) )"
    assert platform.to_xml_element() == b'<?xml version=\'1.0\' encoding=\'utf8\'?>\n<ns0:platform xmlns:ns0="http://cpe.mitre.org/language/2.0" id="systemd_and_chrony_or_ntp_and_not_yum"><ns0:logical-test operator="AND" negate="false"><ns0:logical-test operator="OR" negate="false"><ns0:fact-ref name="cpe:/a:chrony" /><ns0:fact-ref name="cpe:/a:ntp" /></ns0:logical-test><ns0:logical-test operator="AND" negate="true"><ns0:fact-ref name="cpe:/a:yum" /></ns0:logical-test><ns0:fact-ref name="cpe:/a:systemd" /></ns0:logical-test></ns0:platform>'


def test_platform_equality(env_yaml):
    platform1 = ssg.build_yaml.Platform.from_text("ntp or chrony", env_yaml)
    platform2 = ssg.build_yaml.Platform.from_text("chrony or ntp", env_yaml)
    assert platform1 == platform2
    platform3 = ssg.build_yaml.Platform.from_text("(chrony and ntp)", env_yaml)
    platform4 = ssg.build_yaml.Platform.from_text("chrony and ntp", env_yaml)
    assert platform3 == platform4


def test_platform_as_dict(env_yaml):
    pl = ssg.build_yaml.Platform.from_text("chrony and rhel7", env_yaml)
    # represent_as_dict is used during dump_yaml
    d = pl.represent_as_dict()
    assert d["name"] == "chrony_and_rhel7"
    # the "rhel7" platform doesn't have any conditionals
    # therefore the final conditional doesn't use it
    assert d["ansible_conditional"] == "( \"chrony\" in ansible_facts.packages )"
    assert d["bash_conditional"] == "( rpm --quiet -q chrony )"
    assert "xml_content" in d
