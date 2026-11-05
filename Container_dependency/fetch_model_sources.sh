#!/usr/bin/env bash
# Download the model source repositories into Container_dependency/Model_source_codes
# so that the Docker build can run offline, without SSH keys or GitHub access.
#
# Run once (on a machine that has access to the private repos):
#   bash Container_dependency/fetch_model_sources.sh
# Then build without --ssh:
#   docker build -t getm-wad-container:latest .

set -euo pipefail

# Destination folder (next to this script).
DEST="$(cd "$(dirname "$0")" && pwd)/Model_source_codes"
mkdir -p "$DEST"

# clone_at <url> <target dir> <branch name> <remote ref or commit>
clone_at() {
    local url=$1 dir=$2 branch=$3 ref=$4
    if [ -d "$DEST/$dir/.git" ]; then
        echo "Skipping $dir (already present; delete it to re-download)"
        return
    fi
    echo "Cloning $url -> $dir"
    # Keep Unix (LF) line endings, also on Windows with core.autocrlf=true:
    # the sources are built in Linux and the patches expect LF.
    local lf="-c core.autocrlf=false -c core.eol=lf"
    git $lf clone --config core.autocrlf=false --config core.eol=lf "$url" "$DEST/$dir"
    git $lf -C "$DEST/$dir" checkout -b "$branch" "$ref"
    git $lf -C "$DEST/$dir" submodule update --init --recursive
}

# Same branches/commits as used in the Dockerfile.
clone_at git@github.com:jvdmolen/bfm_2016.git bfm_2016 \
    bfm2016_production_20250827 remotes/origin/bfm2016_production_20250827
clone_at git@github.com:jvdmolen/gotm_coupled_bfm_2016.git gotm-git \
    master_20210107_couplingGETM_bfm2016_20241126 remotes/origin/master_20210107_couplingGETM_bfm2016_20241126
clone_at git@github.com:jvdmolen/getm_coupled_bfm_2016.git getm-git \
    iow_20200609_bfm2016_20250116 969dceb73ca9d801c03eb7f218da1d45d5748db3
clone_at https://github.com/fabm-model/fabm.git fabm \
    master_20200610 e1f1f08e42d84f8324f5114924b67ad567719334

echo "All sources are in $DEST"
