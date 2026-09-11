export function BrandMark({className = "h-5 w-5"}: {className?: string}) {
  return (
    // This asset is intentionally served directly instead of through Next's
    // image optimizer so it works behind the Vercel Services route boundary.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src="/branding/job-hunter-mark.png"
      alt="Job Hunter"
      width={1254}
      height={1254}
      className={`${className} object-contain`}
    />
  );
}
