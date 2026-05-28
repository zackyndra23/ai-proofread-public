from app.core import version
from app.core.config import Config


def test_version_info_matches_config():
    info = version.version_info()
    assert info['app_version'] == Config.APP_VERSION
    assert info['api_version'] == Config.API_VERSION
    assert info['build'] == Config.BUILD
    assert info['git_sha'] == Config.GIT_SHA
    assert info['build_at'] == Config.BUILD_AT
