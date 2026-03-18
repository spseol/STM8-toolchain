#!/bin/bash

if [ $1 ]; then
    default=$1
else
    default="stlinkv2"
fi

id=$(lsusb -d 0483: | grep -oP '0483:\K[0-9a-f]+' | head -1)
case "$id" in
  3744) 
      echo "stlink" ;;
  3748) 
      echo "stlinkv2" ;;
  374b) 
      echo "stlinkv21" ;;
  374f) 
      echo "stlinkv3"  ;;
  *) 
      echo "$default";
      exit 1 ;;
esac

exit 0
