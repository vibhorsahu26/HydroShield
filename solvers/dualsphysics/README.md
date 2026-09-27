DualSPHysics 5.4.3 is provisioned into the API image from the official public binary index during the Docker build by default. This directory is intentionally left empty in the source tree so host files cannot mask the image runtime.

Set `HYDROSHIELD_AUTO_PROVISION_DUALSPHYSICS=false` at build time to disable automatic provisioning and provide an external runtime instead.
