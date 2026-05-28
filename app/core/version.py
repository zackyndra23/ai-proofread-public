from .config import Config

def version_info():
  return {
    "app_version": Config.APP_VERSION,
    "api_version": Config.API_VERSION,
    "build": Config.BUILD,
    "git_sha": Config.GIT_SHA,
    "build_at": Config.BUILD_AT,
  }
