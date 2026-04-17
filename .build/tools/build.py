"""
프로젝트 빌드 순서:
1. {project root}/.build/common.json5 를 읽는다.
2. Argument 에서 받아온 레시피 파일 (.json5) 를 읽는다. 구조는 common 과 같다.
3. common 위에 레시피 파일을 업데이트 한다 (레시피 파일이 common 을 override 하지만, 레시피 파일에 없는 값들은 common 에서 가져온다. 하위값 포함.)
4. 위에서 합친것은 레시피 데이터다.
5. 레시피 데이터에서 "Build" 리스트를 읽는다.
6. build 리스트는 src/{build}.debproj 를 가리킨다. (예: "Build": ["app", "lib"] 라면 src/app.debproj, src/lib.debproj 를 가리킨다.)
7. 임시 디렉터리에 src/{build}.debproj 파일들을 복사한다.
8. 레시피 데이터에서 DependencyBuilds 리스트를 읽는다.
9. 리스트의 항목은 dependencies/{element}.json5 를 가리킨다. (예: "DependencyBuilds": ["foo", "bar"] 라면 dependencies/foo.json5, dependencies/bar.json5 를 가리킨다.)
10. 각 json 파일을 읽고, git clone 을 실행한다. (json 파일에는 name, branch, repo 가 있다. git clone {repo} --branch {branch} {name})
11. git clone 한 디렉터리에서 build.sh 파일을 찾아본다. 없다면 .apprunx 를, 그것도 없다면 .debproj 파일을 찾아본다. (build.sh > .apprunx > .debproj)
12. build.sh 파일이 있다면 bash build.sh 을 실행한다. .apprunx 파일이 있다면 그것을 패키징 한다. .debproj 파일이 있다면 그것을 패키징 한다.
13. 레시피 데이터에서 TextSubstitute 딕셔너리를 읽는다
14. 임시로 복사한 모든 non-binary 파일에서 TextSubstitute 딕셔너리에 있는 키를 찾아서 값을 치환한다. (예: "VERSION": "1.0.0" 이 TextSubstitute 에 있다면 모든 non-binary 파일에서 "{{VERSION}}" 을 "1.0.0" 으로 치환한다.)
15. 가장 깊은 곳에 있는 .apprunxproj 혹은 .debproj 파일을 먼저 패키징 한다.
    예: xxxx.apprunxproj/resources/my-files.debproj 가 있다면 my-files.debproj 를 먼저 패키징 하고 그 다음 xxxx.apprunxproj 를 패키징 한다.
       xxxx.debproj/root/my-app.apprunxproj 가 있다면 my-app.apprunxproj 를 먼저 패키징 하고 그 다음 xxxx.debproj 를 패키징 한다.
16. 패키징이 끝나면, 빌드된 모든 deb 파일들을 모두 output/ 디렉터리로 복사한다.
"""


"""
.debproj 빌드 순서
1. .debproj 파일을 읽는다.
2. .debproj 안의 _INFO 의 package.json5 를 읽는다.
3. name, version, depends, conflicts, provides, replaces, architecture, maintainer, description 등의 필드를 읽는다. (일부는 없음)
4. depends, conflicts, provides, replaces 필드에 있는 패키지 이름들을 레시피 데이터의 TextSubstitute 딕셔너리를 이용해서 치환한다. (예: "foo-{{VERSION}}" 이 있다면 "foo-1.0.0" 으로 치환한다.)
5. deb 파일을 만들기 위한 임시 디렉터리를 만든다.
6. _INFO 의 mapping.json 에 따라 디렉터리를 파일들을 구조에 맞추어 임시 디렉터리에 복사한다.
7. deb 파일을 만들기 위한 control 파일을 만든다. (control 파일에는 3번에서 읽은 필드들이 들어간다.)
8. _INFO/preinst.d, _INFO/postinst.d, _INFO/prerm.d, _INFO/postrm.d 디렉터리가 존재한다면, 각각의 디렉터리에 있는 스크립트들을 각각 하나의 파일로 합친 후, control 파일과 함께 deb 파일을 만들 때 사용한다. (예: preinst.d/01-setup.sh, preinst.d/02-config.sh 이 있다면, 두 파일을 합쳐서 deb 파일의 preinst 스크립트로 사용한다.)
9. *.bin.sh 파일은 모두 chmod +x 한 후, .bin.sh 확장자를 제거하여 이름을 변경한다. (예: my-script.bin.sh 는 chmod +x 되고 my-script 로 이름이 변경된다)
10. .py 파일중 맨 앞에 #!/usr/bin/python3 이 있는 파일은 모두 chmod +x 하고 .py 확장자를 제거하여 이름을 변경한다. (예: my-script.py 는 chmod +x 되고 my-script 로 이름이 변경된다)
11. deb 파일을 만든다. (예: dpkg-deb --build {temp_dir} {output_dir}/{package_name}_{version}_{architecture}.deb)
"""