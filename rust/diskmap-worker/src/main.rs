use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::fs::{self, Metadata};
use std::io::{self, BufRead, Write};
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

const PROTOCOL: u8 = 1;

#[derive(Deserialize)]
struct Request {
    protocol: u8,
    root: PathBuf,
    max_entries: u32,
    max_depth: u32,
    max_errors: usize,
    protected_paths: HashSet<String>,
    protected_top_names: HashSet<String>,
    protected_names: HashSet<String>,
}

#[derive(Default, Serialize)]
struct Totals {
    files: u32,
    bytes: u128,
}

impl Totals {
    fn add(&mut self, bytes: u64) {
        self.files += 1;
        self.bytes += u128::from(bytes);
    }
}

#[derive(Serialize)]
struct Branch {
    name: String,
    totals: Totals,
}

#[derive(Serialize)]
struct Skipped {
    path: PathBuf,
    reason: &'static str,
    detail: String,
    os_error: Option<i32>,
}

#[derive(Default, Serialize)]
struct Scan {
    entries: u32,
    dirs: u32,
    links: u32,
    totals: Totals,
    loose: Totals,
    branches: Vec<Branch>,
    error_count: u32,
    errors: Vec<Skipped>,
    truncated: bool,
    #[serde(skip)]
    entry_limit: bool,
}

#[derive(Serialize)]
#[serde(tag = "event", rename_all = "snake_case")]
enum Event<'a> {
    Ready {
        protocol: u8,
    },
    Progress {
        entries: u32,
        files: u32,
        bytes: u128,
    },
    Result {
        scan: &'a Scan,
    },
    ScanError {
        detail: String,
        os_error: Option<i32>,
    },
}

fn emit(output: &mut impl Write, event: Event<'_>) -> io::Result<()> {
    serde_json::to_writer(&mut *output, &event)?;
    output.write_all(b"\n")?;
    output.flush()
}

#[cfg(windows)]
fn is_link(metadata: &Metadata) -> bool {
    use std::os::windows::fs::MetadataExt;
    metadata.file_attributes() & 0x400 != 0 || metadata.file_type().is_symlink()
}

#[cfg(not(windows))]
fn is_link(metadata: &Metadata) -> bool {
    metadata.file_type().is_symlink()
}

struct Walker<'a, W> {
    request: &'a Request,
    output: W,
    last_progress: Instant,
    scan: Scan,
}

impl<W: Write> Walker<'_, W> {
    fn note(&mut self, path: &Path, reason: &'static str, error: Option<io::Error>) {
        self.scan.error_count += 1;
        if self.scan.errors.len() < self.request.max_errors {
            let os_error = error.as_ref().and_then(io::Error::raw_os_error);
            self.scan.errors.push(Skipped {
                path: path
                    .strip_prefix(&self.request.root)
                    .unwrap_or(path)
                    .to_owned(),
                reason,
                detail: error.map_or_else(String::new, |error| error.to_string()),
                os_error,
            });
        }
    }

    fn protected(&self, path: &Path, name: &str, top: bool) -> bool {
        let request = self.request;
        if request.protected_names.is_empty() {
            return false;
        }
        let name = name.to_lowercase();
        request.protected_names.contains(&name)
            || (top && request.protected_top_names.contains(&name))
            || request
                .protected_paths
                .contains(&path.to_string_lossy().to_lowercase())
    }

    fn progress(&mut self) -> io::Result<()> {
        self.last_progress = Instant::now();
        emit(
            &mut self.output,
            Event::Progress {
                entries: self.scan.entries,
                files: self.scan.totals.files,
                bytes: self.scan.totals.bytes,
            },
        )
    }

    fn walk(&mut self, folder: &Path, depth: u32) -> io::Result<Option<Totals>> {
        if depth != 0 {
            match fs::symlink_metadata(folder) {
                Ok(info) if is_link(&info) => {
                    self.scan.links += 1;
                    return Ok(Some(Totals::default()));
                }
                Ok(info) if info.is_dir() => {}
                Ok(_) => {
                    self.note(folder, "changed", None);
                    return Ok(Some(Totals::default()));
                }
                Err(error) => {
                    self.note(folder, "folder", Some(error));
                    return Ok(Some(Totals::default()));
                }
            }
        }
        let entries = match fs::read_dir(folder) {
            Ok(entries) => entries,
            Err(error) => return self.directory_error(folder, depth, error, Totals::default()),
        };
        let mut totals = Totals::default();
        for item in entries {
            let entry = match item {
                Ok(entry) => entry,
                Err(error) => return self.directory_error(folder, depth, error, totals),
            };
            if self.scan.entries == self.request.max_entries {
                self.scan.entry_limit = true;
                self.scan.truncated = true;
                break;
            }
            self.scan.entries += 1;
            if self.scan.entries % 64 == 0
                && self.last_progress.elapsed() >= Duration::from_millis(40)
            {
                self.progress()?;
            }
            let info = match entry.metadata() {
                Ok(info) => info,
                Err(error) => {
                    self.note(&entry.path(), "entry", Some(error));
                    continue;
                }
            };
            if is_link(&info) {
                self.scan.links += 1;
            } else if info.is_file() {
                totals.add(info.len());
                self.scan.totals.add(info.len());
            } else if info.is_dir() {
                let name = entry.file_name();
                let path = entry.path();
                if self.protected(&path, &name.to_string_lossy(), depth == 0) {
                    self.note(&path, "protected", None);
                } else if depth >= self.request.max_depth {
                    self.scan.truncated = true;
                } else {
                    self.scan.dirs += 1;
                    let branch = self
                        .walk(&path, depth + 1)?
                        .expect("only the root can fail the scan");
                    if depth == 0 {
                        let name = name.into_string().map_err(|_| {
                            io::Error::new(
                                io::ErrorKind::InvalidData,
                                "directory name is not Unicode",
                            )
                        })?;
                        self.scan.branches.push(Branch {
                            name,
                            totals: branch,
                        });
                    } else {
                        totals.files += branch.files;
                        totals.bytes += branch.bytes;
                    }
                }
            }
            if self.scan.entry_limit {
                break;
            }
        }
        Ok(Some(totals))
    }

    fn directory_error(
        &mut self,
        folder: &Path,
        depth: u32,
        error: io::Error,
        totals: Totals,
    ) -> io::Result<Option<Totals>> {
        if depth == 0 {
            emit(
                &mut self.output,
                Event::ScanError {
                    detail: error.to_string(),
                    os_error: error.raw_os_error(),
                },
            )?;
            return Ok(None);
        }
        self.note(folder, "folder", Some(error));
        Ok(Some(totals))
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut output = io::BufWriter::new(io::stdout().lock());
    emit(&mut output, Event::Ready { protocol: PROTOCOL })?;
    let mut input = String::new();
    io::stdin().lock().read_line(&mut input)?;
    let request: Request = serde_json::from_str(&input)?;
    if request.protocol != PROTOCOL || !request.root.is_absolute() || request.max_depth > 60 {
        return Err("incompatible Disk Map request".into());
    }
    let mut walker = Walker {
        request: &request,
        output,
        last_progress: Instant::now(),
        scan: Scan::default(),
    };
    if let Some(loose) = walker.walk(&request.root, 0)? {
        walker.scan.loose = loose;
        walker.progress()?;
        emit(&mut walker.output, Event::Result { scan: &walker.scan })?;
    }
    Ok(())
}
