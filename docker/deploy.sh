#!/bin/bash

echo "./deploy.sh $*" > redeploy.sh
chmod +x redeploy.sh

existing=$(docker ps -q -f name='(cryo-em|cryoem)')
if [ -n "$existing" ]; then
    echo "removing existing container"
    docker rm -f $existing
fi

docker run -d \
--name cryoem \
--restart unless-stopped \
-e ARGS="$*" \
cryoem
