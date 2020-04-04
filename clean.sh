if [[ -d "build" ]]
then
	rm -rf build/
fi

if [[ -d "dist" ]]
then
	rm -rf dist/
fi

rm -rf *.spec
