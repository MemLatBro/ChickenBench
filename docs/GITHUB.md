# Put this folder on GitHub

The extracted `ChickenBench-v1.0.8/` folder is the repository root: it contains
`README.md`, `LICENSE`, the launch buttons, and the grouped source directories.

## First upload

1. Create an empty GitHub repository with the name you want, such as `ChickenBench`.
   Do not have GitHub generate another README, license, or gitignore; they are
   already supplied here.
2. Open the extracted folder in GitHub Desktop, add it as a local repository,
   create the initial commit, and choose **Publish repository**. This preserves
   dotfiles such as `.gitignore` and `.github/workflows/tests.yml`.
3. Choose public visibility when you are ready to publish.

If you prefer the Git command line, create the empty remote repository first,
then run these from this folder. Replace `YOUR-ACCOUNT` with the actual account
or organization and use the repository URL GitHub gives you:

```sh
git init -b main
git add .
git commit -m "Prepare ChickenBench 1.0.8"
git remote add origin https://github.com/YOUR-ACCOUNT/ChickenBench.git
git push -u origin main
```

## Source and downloadable releases

Commit the extracted source tree. A ZIP alone is not a browsable source repository.
GitHub Actions is configured to run offline tests after pushes and pull requests;
check its actual results rather than assuming the configuration has already run.

Build a release ZIP locally with `python scripts/build_release.py`. Attach the
result from `dist/` to a GitHub Release for a tag such as `v1.0.8`, or let users
download GitHub's source archive. A separate ZIP attachment is optional.

Keep PresentMon and the original Workshop addon separately installed. Local
captures, binaries, caches, and built ZIPs are excluded from the source package
and normal Git tracking. Existing example reports and test fixtures are included.

The MIT license permits free use, modification, redistribution, and commercial
use of the covered code, with notice preservation. The third-party exclusions
are described in `THIRD_PARTY_NOTICES.md`; the license makes no claim of approval
from Valve or the Workshop contributors.
